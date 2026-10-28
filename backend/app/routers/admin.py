from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import accessible_project_ids, authorize, current_user, ensure_operational_project, require_superuser
from ..member_import import apply_import, import_template, parse_import_file, validate_import_rows
from ..models import Machine, Permission, Project, ProjectMember, Role, Subsystem, User, Version
from ..schemas import BulkImportInput, EntityInput, GlobalRoleInput, MemberInput, RoleInput, UserInput
from ..services import audit, commit

router = APIRouter(tags=['系统管理与基础数据'])
resources = {'projects': Project, 'versions': Version, 'machines': Machine, 'subsystems': Subsystem}
business_permissions = {
    'versions': 'business.version',
    'machines': 'business.machine',
    'subsystems': 'business.subsystem',
}


def entity_out(item) -> dict:
    return {c.name: getattr(item, c.name) for c in item.__table__.columns}


def user_out(item: User) -> dict:
    return {'id': item.id, 'username': item.username, 'employee_id': item.employee_id,
            'department': item.department, 'email': item.email, 'is_superuser': item.is_superuser}


def directory_user_out(item: User) -> dict:
    return {'id': item.id, 'username': item.username, 'employee_id': item.employee_id,
            'department': item.department, 'email': item.email}


def require_role_read(db: Session, user: User, project_id: str | None) -> None:
    if not user.is_superuser:
        if not project_id:
            raise HTTPException(422, '项目成员查看角色时必须指定项目')
        authorize(db, user, 'project.role.view', project_id)


def assignable_role(db: Session, role_id: str) -> Role:
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, '项目角色不存在')
    if role.name in {'系统管理员', '初始化用户'}:
        raise HTTPException(403, f'{role.name}不是可分配的项目角色')
    return role


def ensure_member_editable(actor: User, member: ProjectMember) -> None:
    if not actor.is_superuser and (member.user.is_superuser or member.role.name == '系统管理员'):
        raise HTTPException(403, '项目管理员不能修改或移除系统管理员')


def ensure_project_admin_retained(db: Session, project_id: str, member: ProjectMember, new_role_id: str | None = None) -> None:
    if member.role.name != '项目管理员' or new_role_id == member.role_id:
        return
    # Serialize admin changes per project so two concurrent demotions cannot remove both admins.
    db.get(Project, project_id, with_for_update=True)
    count = db.scalar(select(func.count(ProjectMember.id)).join(Role, ProjectMember.role_id == Role.id).where(
        ProjectMember.project_id == project_id, Role.name == '项目管理员'))
    if (count or 0) <= 1:
        raise HTTPException(409, '项目必须至少保留一名项目管理员')


@router.get('/bootstrap/options', summary='获取可访问项目及版本、机台、子系统、责任人与可分配角色选项')
def options(project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    projects = db.scalars(select(Project)).all()
    allowed = accessible_project_ids(db, user)
    if allowed is not None:
        projects = [x for x in projects if x.id in allowed]
    accessible = {x.id for x in projects}
    if project_id and project_id not in accessible:
        raise HTTPException(403, '你无权访问该项目')
    roles = db.scalars(select(Role)).all()
    if not user.is_superuser:
        roles = [role for role in roles if role.name != '系统管理员']
    result = {'projects': [entity_out(x) for x in projects], 'roles': [entity_out(x) for x in roles]}
    for name, model in [('versions', Version), ('machines', Machine), ('subsystems', Subsystem)]:
        query = select(model)
        if project_id:
            query = query.where(model.project_id == project_id)
        else:
            query = query.where(model.project_id.in_(accessible))
        result[name] = [entity_out(x) for x in db.scalars(query).all()]
    member_query = select(ProjectMember)
    if project_id:
        member_query = member_query.where(ProjectMember.project_id == project_id)
    else:
        member_query = member_query.where(ProjectMember.project_id.in_(accessible))
    members = db.scalars(member_query).unique().all()
    users = {x.user.id: x.user for x in members}
    if allowed is None:
        global_users = db.scalars(select(User).where(User.is_active.is_(True), User.global_role_id.is_not(None))).all()
        users.update({x.id: x for x in global_users})
    users[user.id] = user
    result['users'] = [{'id': x.id, 'username': x.username, 'employee_id': x.employee_id, 'department': x.department, 'email': x.email} for x in users.values()]
    return result


@router.get('/business/{resource}', summary='查询项目、版本、机台或子系统列表')
def list_business(resource: str, project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    model = resources.get(resource)
    if not model:
        raise HTTPException(404, '未知业务资源')
    query = select(model)
    if resource == 'projects':
        allowed = accessible_project_ids(db, user)
        if allowed is not None:
            query = query.where(model.id.in_(allowed))
    else:
        if not project_id and not user.is_superuser:
            raise HTTPException(422, '必须指定所属项目')
        authorize(db, user, f'{business_permissions[resource]}.view', project_id)
        if project_id:
            query = query.where(model.project_id == project_id)
    return [entity_out(x) for x in db.scalars(query).all()]


@router.post('/business/{resource}', status_code=201, summary='新增项目、版本、机台或子系统')
def create_business(resource: str, payload: EntityInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    model = resources.get(resource)
    if not model:
        raise HTTPException(404, '未知业务资源')
    if resource == 'projects':
        require_superuser(user)
    else:
        if not payload.project_id:
            raise HTTPException(422, '必须指定所属项目')
        authorize(db, user, f'{business_permissions[resource]}.edit', payload.project_id)
        ensure_operational_project(db, payload.project_id)
    values = payload.model_dump(exclude_none=True)
    if resource == 'versions':
        values['number'] = payload.number or payload.name
        values.pop('name', None)
    if resource == 'projects':
        values.pop('project_id', None)
    item = model(**values)
    db.add(item)
    db.flush()
    audit(db, user, 'BUSINESS_CREATE', resource, item.id)
    commit(db)
    return entity_out(item)


@router.put('/business/{resource}/{item_id}', summary='修改业务基础数据')
def update_business(resource: str, item_id: str, payload: EntityInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    model = resources.get(resource)
    if not model:
        raise HTTPException(404, '未知业务资源')
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(404, '数据不存在')
    if resource == 'projects':
        require_superuser(user)
    else:
        authorize(db, user, f'{business_permissions[resource]}.edit', item.project_id)
        ensure_operational_project(db, item.project_id)
        if payload.project_id and payload.project_id != item.project_id:
            raise HTTPException(403, '不允许将业务数据转移到其他项目')
    excluded = {'name'} if resource == 'versions' else set()
    if resource != 'projects':
        excluded = {*excluded, 'project_id'}
    for key, value in payload.model_dump(exclude_none=True, exclude=excluded).items():
        if hasattr(item, key):
            setattr(item, key, value)
    if resource == 'versions':
        item.number = payload.number or payload.name
    audit(db, user, 'BUSINESS_UPDATE', resource, item.id)
    commit(db)
    return entity_out(item)


@router.delete('/business/{resource}/{item_id}', summary='删除未被引用的业务基础数据')
def delete_business(resource: str, item_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    model = resources.get(resource)
    if not model:
        raise HTTPException(404, '未知业务资源')
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(404, '数据不存在')
    if resource == 'projects':
        require_superuser(user)
    else:
        authorize(db, user, f'{business_permissions[resource]}.edit', item.project_id)
        ensure_operational_project(db, item.project_id)
    audit(db, user, 'BUSINESS_DELETE', resource, item.id)
    db.delete(item)
    commit(db)
    return {'message': '删除成功'}


@router.get('/users', summary='按用户名、工号或部门搜索可加入当前项目的平台用户')
def list_users(q: str | None = None, project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not user.is_superuser:
        if not project_id:
            raise HTTPException(422, '搜索平台用户时必须指定项目')
        authorize(db, user, 'project.member.view', project_id)
    query = select(User).where(User.is_active.is_(True), User.is_superuser.is_(False))
    if q:
        query = query.where((User.username.ilike(f'%{q}%')) | (User.employee_id.ilike(f'%{q}%')) | (User.department.ilike(f'%{q}%')))
    return [directory_user_out(x) for x in db.scalars(query).all()]


@router.post('/users', status_code=201, summary='预创建本地用户（仅系统管理员，不自动分配项目权限）')
def create_user(payload: UserInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_superuser(user)
    item = User(**payload.model_dump())
    db.add(item)
    db.flush()
    audit(db, user, 'USER_CREATE', 'user', item.id)
    commit(db)
    return user_out(item)


@router.get('/global-access/users', summary='查询平台用户的所有项目角色授权（仅系统管理员）')
def global_access_users(db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_superuser(user)
    rows = db.scalars(select(User).where(User.is_active.is_(True), User.is_superuser.is_(False))).all()
    return [{**directory_user_out(x), 'email': x.email, 'global_role_id': x.global_role_id,
             'global_role': x.global_role.name if x.global_role else None} for x in rows]


@router.put('/users/{user_id}/global-role', summary='授予或撤销用户的所有项目角色（仅系统管理员）')
def update_global_role(user_id: str, payload: GlobalRoleInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_superuser(user)
    item = db.get(User, user_id)
    if not item or not item.is_active or item.is_superuser:
        raise HTTPException(404, '可授权的平台用户不存在')
    if payload.role_id:
        assignable_role(db, payload.role_id)
    item.global_role_id = payload.role_id
    audit(db, user, 'GLOBAL_ROLE_UPDATE', 'user', item.id, {'role_id': payload.role_id})
    commit(db)
    return {'message': '所有项目授权已更新', 'global_role_id': item.global_role_id}


@router.get('/projects/{project_id}/members', summary='查询项目成员及项目角色')
def members(project_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'project.member.view', project_id)
    rows = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id)).all()
    return [{'id': x.id, 'project_id': x.project_id, 'role_id': x.role_id, 'role': x.role.name,
             'user': {'id': x.user.id, 'username': x.user.username, 'employee_id': x.user.employee_id,
                      'department': x.user.department, 'email': x.user.email}} for x in rows]


@router.get('/projects/{project_id}/members/import-template', summary='下载项目用户批量初始化 Excel 模板')
def download_import_template(project_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'project.member.manage', project_id)
    return Response(content=import_template(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename=wmp-member-import-template.xlsx'})


@router.post('/projects/{project_id}/members/bulk-preview', summary='解析并校验批量初始化文件，返回逐行预览')
async def preview_import(project_id: str, default_role_id: str = Form(...), file: UploadFile = File(...),
                         db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'project.member.manage', project_id)
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(422, '导入文件不能超过 10 MB')
    rows = parse_import_file(content, file.filename or '')
    result = validate_import_rows(db, project_id, default_role_id, rows)
    return {'summary': result['summary'], 'rows': result['rows']}


@router.post('/projects/{project_id}/members/bulk-import', summary='确认批量创建平台用户并初始化当前项目成员')
def bulk_import(project_id: str, payload: BulkImportInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'project.member.manage', project_id)
    result = apply_import(db, project_id, payload.default_role_id, [row.model_dump() for row in payload.rows])
    summary = result['summary']
    audit(db, user, 'MEMBER_BULK_IMPORT', 'project', project_id, summary)
    commit(db)
    return {'message': '批量初始化完成', **result}


@router.post('/projects/{project_id}/members', status_code=201, summary='添加项目成员并分配非全局项目角色')
def add_member(project_id: str, payload: MemberInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'project.member.manage', project_id)
    assignable_role(db, payload.role_id)
    member_user = db.get(User, payload.user_id)
    if not member_user or not member_user.is_active or member_user.is_superuser:
        raise HTTPException(422, '只能添加已启用且非系统管理员的平台用户')
    item = ProjectMember(project_id=project_id, user_id=payload.user_id, role_id=payload.role_id)
    db.add(item)
    audit(db, user, 'MEMBER_ADD', 'project', project_id, {'member_user_id': payload.user_id})
    commit(db)
    return {'id': item.id, **payload.model_dump()}


@router.put('/projects/{project_id}/members/{member_id}', summary='调整成员在当前项目中的角色')
def update_member(project_id: str, member_id: str, payload: MemberInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'project.member.manage', project_id)
    item = db.get(ProjectMember, member_id)
    if not item or item.project_id != project_id:
        raise HTTPException(404, '项目成员不存在')
    assignable_role(db, payload.role_id)
    ensure_member_editable(user, item)
    ensure_project_admin_retained(db, project_id, item, payload.role_id)
    item.role_id = payload.role_id
    audit(db, user, 'MEMBER_ROLE_UPDATE', 'project', project_id, {'member_id': member_id})
    commit(db)
    return {'message': '成员角色已更新'}


@router.delete('/projects/{project_id}/members/{member_id}', summary='将成员移出项目')
def remove_member(project_id: str, member_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'project.member.manage', project_id)
    item = db.get(ProjectMember, member_id)
    if not item or item.project_id != project_id:
        raise HTTPException(404, '项目成员不存在')
    ensure_member_editable(user, item)
    ensure_project_admin_retained(db, project_id, item)
    db.delete(item)
    audit(db, user, 'MEMBER_REMOVE', 'project', project_id, {'member_id': member_id})
    commit(db)
    return {'message': '成员已移出项目'}


@router.get('/roles', summary='查询全局角色模板及按钮权限点（项目成员只读）')
def roles(project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role_read(db, user, project_id)
    return [{'id': x.id, 'name': x.name, 'description': x.description, 'built_in': x.built_in,
             'permissions': [p.code for p in x.permissions]} for x in db.scalars(select(Role)).all()]


@router.get('/permissions', summary='获取全部可配置项目权限点（项目成员只读）')
def all_permissions(project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_role_read(db, user, project_id)
    return [entity_out(x) for x in db.scalars(select(Permission).order_by(Permission.module, Permission.code)).all()]


@router.post('/roles', status_code=201, summary='新增全局自定义角色（仅系统管理员）')
def create_role(payload: RoleInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_superuser(user)
    if payload.name in {'系统管理员', '初始化用户'}:
        raise HTTPException(409, f'{payload.name}是保留角色')
    item = Role(name=payload.name, description=payload.description, built_in=False)
    item.permissions = db.scalars(select(Permission).where(Permission.code.in_(payload.permissions))).all()
    db.add(item)
    audit(db, user, 'ROLE_CREATE', 'role', item.name)
    commit(db)
    return {'id': item.id, 'name': item.name, 'permissions': [p.code for p in item.permissions]}


@router.put('/roles/{role_id}', summary='编辑全局角色及按钮权限（仅系统管理员）')
def update_role(role_id: str, payload: RoleInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_superuser(user)
    item = db.get(Role, role_id)
    if not item:
        raise HTTPException(404, '角色不存在')
    if item.name in {'系统管理员', '初始化用户'} or payload.name in {'系统管理员', '初始化用户'}:
        raise HTTPException(409, '系统管理员和初始化用户角色不可通过项目角色接口修改')
    item.name = payload.name
    item.description = payload.description
    item.permissions = db.scalars(select(Permission).where(Permission.code.in_(payload.permissions))).all()
    audit(db, user, 'ROLE_UPDATE', 'role', item.id)
    commit(db)
    return {'message': '角色权限已保存'}


@router.delete('/roles/{role_id}', summary='删除未被使用的全局自定义角色（仅系统管理员）')
def delete_role(role_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_superuser(user)
    item = db.get(Role, role_id)
    if not item:
        raise HTTPException(404, '角色不存在')
    if item.built_in:
        raise HTTPException(409, '预设角色不可删除')
    if db.scalar(select(ProjectMember).where(ProjectMember.role_id == role_id)):
        raise HTTPException(409, '角色仍被项目成员使用')
    if db.scalar(select(User).where(User.global_role_id == role_id)):
        raise HTTPException(409, '角色仍被全局统计授权用户使用')
    db.delete(item)
    audit(db, user, 'ROLE_DELETE', 'role', role_id)
    commit(db)
    return {'message': '角色已删除'}
