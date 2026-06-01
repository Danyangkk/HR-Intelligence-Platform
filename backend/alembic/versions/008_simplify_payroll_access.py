"""008 simplify payroll access — 薪资权=业务超管角色自带

Revision ID: 008
Revises: 007
Create Date: 2026-05-28

新规格：
- 薪资访问权随业务超管角色自带，不单独授予
- 技术超管、普通员工永久无薪资权
- 清理旧演示账号 sys_admin（如果存在）

"""
from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 清理技术超管和普通员工的 payroll_access（确保与新规格一致）
    op.execute(
        """
        UPDATE users 
        SET payroll_access = false 
        WHERE role IN ('tech_super_admin', 'staff')
        """
    )
    
    # 确保业务超管有 payroll_access（虽然逻辑上只看角色，但保持数据一致性）
    op.execute(
        """
        UPDATE users 
        SET payroll_access = true 
        WHERE role = 'biz_super_admin'
        """
    )
    
    # 删除旧演示账号 sys_admin（如果存在）
    op.execute("DELETE FROM users WHERE username = 'sys_admin'")


def downgrade() -> None:
    # 降级不恢复数据
    pass
