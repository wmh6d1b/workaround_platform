from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import authorize, current_user
from ..models import Machine, Permission, Project, ProjectMember, Role, RolePermission, Subsystem, User, Version
from ..schemas import EntityInput, MemberInput, RoleInput, UserInput
from ..services import audit, commit

router = APIRouter(tags=['系统管理与基础数据'])
resources = {'projects': Project, 'versions': Version, 'machines': Machine, 'subsystems': Subsystem}

def entity_out(item) -> dict:
    return {c.name: getattr(item, c.name) for c in item.__table__.columns}

def user_out(item: User) -> dict:
    return {'id': item.id, 'username': item.username, 'employee_id': item.employee_id,
            'name': item.name, 'email': item.email, 'is_superuser': item.is_superuser}

@router.get('/bootstrap/options', summary='获取可访问项目及版本、机台、子系统、责任人与角色选项')
def options(project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    projects = db.scalars(select(Project)).all()
    if not user.is_superuser:
        allowed = set(db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)).all())
        projects = [x for x in projects if x.id in allowed]
    accessible = {x.id for x in projects}
    if project_id and project_id not in accessible:
        raise HTTPException(403, '你不是该项目成员')
    result = {'projects': [entity_out(x) for x in projects], 'roles': [entity_out(x) for x in db.scalars(select(Role)).all()]}
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
    if user.is_superuser: users[user.id] = user
    result['users'] = [{'id': x.id, 'name': x.name, 'username': x.username, 'employee_id': x.employee_id, 'email': x.email} for x in users.values()]
    return result

@router.get('/business/{resource}', summary='查询项目、版本、机台或子系统列表')
def list_business(resource: str, project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    model = resources.get(resource)
    if not model: raise HTTPException(404, '未知业务资源')
    authorize(db, user, 'system.business.view', project_id)
    query = select(model)
    if project_id and resource != 'projects':
        query = query.where(model.project_id == project_id)
    elif not user.is_superuser:
        allowed = set(db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)).all())
        query = query.where(model.id.in_(allowed) if resource == 'projects' else model.project_id.in_(allowed))
    return [entity_out(x) for x in db.scalars(query).all()]

@router.post('/business/{resource}', status_code=201, summary='新增项目、版本、机台或子系统')
def create_business(resource: str, payload: EntityInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    model = resources.get(resource)
    if not model: raise HTTPException(404, '未知业务资源')
    authorize(db, user, 'system.business.edit', payload.project_id)
    values = payload.model_dump(exclude_none=True)
    if resource == 'versions': values['number'] = payload.number or payload.name
    if resource == 'versions': values.pop('name', None)
    if resource == 'projects': values.pop('project_id', None)
    if resource != 'projects' and not payload.project_id: raise HTTPException(422, '必须指定所属项目')
    item = model(**values)
    db.add(item)
    db.flush()
    audit(db, user, 'BUSINESS_CREATE', resource, item.id)
    commit(db)
    return entity_out(item)

@router.put('/business/{resource}/{item_id}', summary='修改业务基础数据')
def update_business(resource: str, item_id: str, payload: EntityInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    model = resources.get(resource)
    if not model: raise HTTPException(404, '未知业务资源')
    item = db.get(model, item_id)
    if not item: raise HTTPException(404, '数据不存在')
    project_id = item.id if resource == 'projects' else item.project_id
    authorize(db, user, 'system.business.edit', project_id)
    for key, value in payload.model_dump(exclude_none=True, exclude={'name'} if resource == 'versions' else set()).items():
        if hasattr(item, key): setattr(item, key, value)
    if resource == 'versions': item.number = payload.number or payload.name
    audit(db, user, 'BUSINESS_UPDATE', resource, item.id)
    commit(db)
    return entity_out(item)

@router.delete('/business/{resource}/{item_id}', summary='删除未被引用的业务基础数据')
def delete_business(resource: str, item_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    model = resources.get(resource)
    if not model: raise HTTPException(404, '未知业务资源')
    item = db.get(model, item_id)
    if not item: raise HTTPException(404, '数据不存在')
    authorize(db, user, 'system.business.edit', item.id if resource == 'projects' else item.project_id)
    audit(db, user, 'BUSINESS_DELETE', resource, item.id)
    db.delete(item)
    commit(db)
    return {'message': '删除成功'}

@router.get('/users', summary='按姓名、用户名或工号查询平台用户')
def list_users(q: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.member.view')
    query = select(User)
    if q: query = query.where((User.name.ilike(f'%{q}%')) | (User.username.ilike(f'%{q}%')) | (User.employee_id.ilike(f'%{q}%')))
    return [user_out(x) for x in db.scalars(query).all()]

@router.post('/users', status_code=201, summary='预创建本地用户（不自动分配项目权限）')
def create_user(payload: UserInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.member.edit')
    item = User(**payload.model_dump())
    db.add(item)
    db.flush()
    audit(db, user, 'USER_CREATE', 'user', item.id)
    commit(db)
    return user_out(item)

@router.get('/projects/{project_id}/members', summary='查询项目成员及项目角色')
def members(project_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.member.view', project_id)
    rows = db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id)).all()
    return [{'id': x.id, 'project_id': x.project_id, 'role_id': x.role_id, 'role': x.role.name,
             'user': {'id': x.user.id, 'name': x.user.name, 'username': x.user.username, 'employee_id': x.user.employee_id, 'email': x.user.email}} for x in rows]

@router.post('/projects/{project_id}/members', status_code=201, summary='添加项目成员并分配角色')
def add_member(project_id: str, payload: MemberInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.member.edit', project_id)
    item = ProjectMember(project_id=project_id, user_id=payload.user_id, role_id=payload.role_id)
    db.add(item)
    audit(db, user, 'MEMBER_ADD', 'project', project_id, {'member_user_id': payload.user_id})
    commit(db)
    return {'id': item.id, **payload.model_dump()}

@router.put('/projects/{project_id}/members/{member_id}', summary='调整成员在当前项目中的角色')
def update_member(project_id: str, member_id: str, payload: MemberInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.member.edit', project_id)
    item = db.get(ProjectMember, member_id)
    if not item or item.project_id != project_id: raise HTTPException(404, '项目成员不存在')
    item.role_id = payload.role_id
    audit(db, user, 'MEMBER_ROLE_UPDATE', 'project', project_id, {'member_id': member_id})
    commit(db)
    return {'message': '成员角色已更新'}

@router.delete('/projects/{project_id}/members/{member_id}', summary='将成员移出项目')
def remove_member(project_id: str, member_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.member.edit', project_id)
    item = db.get(ProjectMember, member_id)
    if not item or item.project_id != project_id: raise HTTPException(404, '项目成员不存在')
    db.delete(item)
    audit(db, user, 'MEMBER_REMOVE', 'project', project_id, {'member_id': member_id})
    commit(db)
    return {'message': '成员已移出项目'}

@router.get('/roles', summary='查询角色及按钮权限点')
def roles(db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.role.view')
    return [{'id': x.id, 'name': x.name, 'description': x.description, 'built_in': x.built_in,
             'permissions': [p.code for p in x.permissions]} for x in db.scalars(select(Role)).all()]

@router.get('/permissions', summary='获取全部可配置按钮权限点')
def all_permissions(db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.role.view')
    return [entity_out(x) for x in db.scalars(select(Permission).order_by(Permission.module, Permission.code)).all()]

@router.post('/roles', status_code=201, summary='新增自定义角色')
def create_role(payload: RoleInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.role.edit')
    item = Role(name=payload.name, description=payload.description, built_in=False)
    item.permissions = db.scalars(select(Permission).where(Permission.code.in_(payload.permissions))).all()
    db.add(item)
    audit(db, user, 'ROLE_CREATE', 'role', item.name)
    commit(db)
    return {'id': item.id, 'name': item.name, 'permissions': [p.code for p in item.permissions]}

@router.put('/roles/{role_id}', summary='编辑角色及按钮权限')
def update_role(role_id: str, payload: RoleInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.role.edit')
    item = db.get(Role, role_id)
    if not item: raise HTTPException(404, '角色不存在')
    item.name = payload.name
    item.description = payload.description
    item.permissions = db.scalars(select(Permission).where(Permission.code.in_(payload.permissions))).all()
    audit(db, user, 'ROLE_UPDATE', 'role', item.id)
    commit(db)
    return {'message': '角色权限已保存'}

@router.delete('/roles/{role_id}', summary='删除未被使用的自定义角色')
def delete_role(role_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'system.role.edit')
    item = db.get(Role, role_id)
    if not item: raise HTTPException(404, '角色不存在')
    if item.built_in: raise HTTPException(409, '预设角色不可删除')
    if db.scalar(select(ProjectMember).where(ProjectMember.role_id == role_id)): raise HTTPException(409, '角色仍被项目成员使用')
    db.delete(item)
    audit(db, user, 'ROLE_DELETE', 'role', role_id)
    commit(db)
    return {'message': '角色已删除'}
