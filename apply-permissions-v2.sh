#!/bin/bash
# 权限重构 V2 - 一键应用脚本

set -e

echo "======================================"
echo "权限重构 V2 - 应用新权限模型"
echo "======================================"
echo ""

cd "$(dirname "$0")/backend"

echo "1️⃣  运行数据库迁移..."
alembic upgrade head

echo ""
echo "2️⃣  重新 seed 演示用户（清理 sys_admin，确保新模型一致）..."
python -m src.seed.run

echo ""
echo "✅ 权限重构 V2 应用完成！"
echo ""
echo "演示账号："
echo "  • tech_admin/tech123  - 技术超管，永久无薪资权"
echo "  • biz_hrd/hrd123      - 业务超管[🔑]，岗位自带薪资权"
echo "  • staff1/staff123     - 普通员工，永久薪资隔离"
echo ""
echo "启动后端："
echo "  cd backend"
echo "  PYTHONPATH=.. python3.11 -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000"
echo ""
echo "前端访问："
echo "  http://localhost:8080"
echo ""
echo "详细验证指南："
echo "  cat VERIFY_PERMISSIONS_V2.md"
echo ""
