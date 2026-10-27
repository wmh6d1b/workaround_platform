from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .models import ExecutionType, Machine, Permission, Project, ProjectMember, Role, Subsystem, User, Version, Wkd, WkdStatus
from .security import hash_password
from .services import commit

PERMISSIONS = {
    'home.view': '查看首页', 'wkd.view': '查看 WKD', 'wkd.create': '新建 WKD', 'wkd.edit': '编辑 WKD',
    'wkd.submit': '提交自验证或审核', 'wkd.review': '软件经理审核', 'wkd.disable': '禁用 WKD', 'wkd.note': '填写状态说明',
    'build.debug.view': '查看调试构建', 'build.debug.build': '执行调试构建', 'build.release.view': '查看正式构建和制品',
    'build.release.build': '执行正式构建', 'build.release.download': '下载构建制品',
    'business.version.view': '查看版本管理', 'business.version.edit': '维护版本数据',
    'business.machine.view': '查看机台管理', 'business.machine.edit': '维护机台数据',
    'business.subsystem.view': '查看子系统管理', 'business.subsystem.edit': '维护子系统数据',
    'project.member.view': '查看项目成员', 'project.member.manage': '管理项目成员及角色分配',
    'project.role.view': '查看项目角色权限', 'files.upload': '上传附件', 'files.download': '下载附件',
}
ROLE_CODES = {
    '开发人员': {'home.view','wkd.view','wkd.create','wkd.edit','wkd.submit','wkd.disable','wkd.note','build.debug.view','build.debug.build','build.release.view','build.release.download','files.upload','files.download'},
    '软件经理': {'home.view','wkd.view','wkd.edit','wkd.review','wkd.disable','wkd.note','build.debug.view','build.debug.build','build.release.view','build.release.download','files.upload','files.download'},
    '项目管理员': set(PERMISSIONS),
    '系统管理员': set(PERMISSIONS),
}
LEGACY_PERMISSION_MAP = {
    'system.business.view': {'business.version.view', 'business.machine.view', 'business.subsystem.view'},
    'system.business.edit': {'business.version.edit', 'business.machine.edit', 'business.subsystem.edit'},
    'system.member.view': {'project.member.view'},
    'system.member.edit': {'project.member.manage'},
    'system.role.view': {'project.role.view'},
    'system.role.edit': set(),
}


def migrate_legacy_permissions(db: Session, permissions: dict[str, Permission], roles: list[Role]) -> None:
    """Map legacy project-role permissions once and remove all global-role grants."""
    for role in roles:
        codes = {permission.code for permission in role.permissions}
        legacy = codes.intersection(LEGACY_PERMISSION_MAP)
        if not legacy:
            continue
        migrated = codes.difference(LEGACY_PERMISSION_MAP)
        for code in legacy:
            migrated.update(LEGACY_PERMISSION_MAP[code])
        role.permissions = [permissions[code] for code in migrated if code in permissions]
    for code in LEGACY_PERMISSION_MAP:
        permission = permissions.get(code)
        if permission:
            db.delete(permission)
    db.flush()


def seed(db: Session) -> None:
    for code, description in PERMISSIONS.items():
        if not db.get(Permission, code):
            db.add(Permission(code=code, module=code.split('.')[0], description=description))
    db.flush()
    permissions = {x.code: x for x in db.scalars(select(Permission)).all()}
    existing_roles = list(db.scalars(select(Role)).all())
    migrate_legacy_permissions(db, permissions, existing_roles)
    # 统计已对所有登录用户开放，清理旧版本及未完成方案中的统计权限点。
    removed_statistics_permissions = {'stats.view', 'stats.export', 'stats.global.view', 'stats.global.export'}
    for role in existing_roles:
        role.permissions = [permission for permission in role.permissions if permission.code not in removed_statistics_permissions]
    for code in removed_statistics_permissions:
        if code in permissions:
            db.delete(permissions[code])
    db.flush()
    roles = {role.name: role for role in existing_roles}
    for name, codes in ROLE_CODES.items():
        role = roles.get(name)
        if not role:
            role = Role(name=name, description=f'WMP 预设角色：{name}', built_in=True)
            role.permissions = [permissions[x] for x in codes]
            db.add(role)
        roles[name] = role
    settings = get_settings()
    admin = db.scalar(select(User).where(User.username == settings.bootstrap_admin_username))
    if not admin:
        admin = User(username=settings.bootstrap_admin_username, employee_id='E0001', name='系统管理员',
                    password_hash=hash_password(settings.bootstrap_admin_password), is_superuser=True)
        db.add(admin)
        db.flush()
    if settings.seed_demo_data and not db.scalar(select(Project.id).limit(1)):
        project = Project(name='晶圆检测设备', code='WAFER-INSPECT', owner_id=admin.id)
        db.add(project)
        db.flush()
        version = Version(project_id=project.id, number='V3.2.0', owner_id=admin.id)
        machines = [Machine(project_id=project.id, name=f'AQ-{n}', model='AQ 系列', owner_id=admin.id) for n in (1000, 2000, 3000)]
        subsystem = Subsystem(project_id=project.id, name='运动控制', code='MOTION', owner_id=admin.id)
        db.add_all([version, subsystem, *machines])
        db.flush()
        db.add(ProjectMember(project_id=project.id, user_id=admin.id, role_id=roles['系统管理员'].id))
        db.add(Wkd(number='WKD202610260001', title='修复晶圆加载后坐标偏移问题', description='在初始化阶段补偿机械坐标偏移量。',
                   requirement_no='REQ-2026-001', project_id=project.id, version_id=version.id, subsystem_id=subsystem.id,
                   owner_id=admin.id, execution_type=ExecutionType.MANUAL, activity_scene='常规版本升级', measure_type='事前规避措施',
                   status=WkdStatus.APPROVED, machines=[machines[1]]))
    commit(db)
