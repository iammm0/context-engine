# 数据模型迁移脚本说明

## 概述

`migrate_models.py` 是一个通用的数据模型迁移脚本，用于：
- 初始化数据库结构（MongoDB索引、Neo4j索引）
- 执行数据模型版本迁移
- 记录迁移历史
- 支持选择性运行特定迁移

## 使用方法

### 1. 运行所有未应用的迁移

```bash
cd context-engine
python scripts/migrate_models.py
```

### 2. 查看迁移状态

```bash
python scripts/migrate_models.py --status
```

### 3. 运行指定的迁移

```bash
python scripts/migrate_models.py --migrations 001_create_mongodb_indexes 002_create_neo4j_indexes
```

### 4. 强制重新运行已应用的迁移

```bash
python scripts/migrate_models.py --force
```

### 5. 在Docker容器中运行

```bash
# 进入容器
docker exec -it context-engine-1 bash

# 运行迁移
python scripts/migrate_models.py
```

## 迁移列表

### 001_create_mongodb_indexes
- **名称**: 创建MongoDB索引
- **描述**: 为用户、助手、文档、资源等集合创建必要的索引
- **版本**: 1.0.0
- **影响**: 提升查询性能，不影响现有数据

### 002_create_neo4j_indexes
- **名称**: 创建Neo4j索引
- **描述**: 为Neo4j图数据库创建用户节点索引
- **版本**: 1.0.0
- **影响**: 提升图查询性能，不影响现有数据

### 003_migrate_user_model_fields
- **名称**: 迁移用户模型字段
- **描述**: 为现有用户添加新字段的默认值（如profile_visibility、research_fields等）
- **版本**: 1.0.0
- **影响**: 为现有用户添加新字段，不删除或修改现有数据

### 004_migrate_resource_schema_version
- **名称**: 迁移资源模型版本
- **描述**: 将旧版本资源迁移到新版本schema（添加schema_version字段）
- **版本**: 1.0.0
- **影响**: 更新资源的schema_version字段，不删除或修改其他数据

## 迁移历史

迁移历史记录在MongoDB的 `migration_history` 集合中，包含：
- `migration_id`: 迁移ID
- `status`: 状态（pending, completed, failed）
- `applied_at`: 应用时间
- `error`: 错误信息（如果有）

## 添加新迁移

要添加新的迁移，在 `MigrationManager._register_migrations()` 方法中添加：

```python
self.migrations.append({
    "id": "005_new_migration",
    "name": "新迁移名称",
    "description": "迁移描述",
    "version": "1.0.0",
    "migrate": self._migrate_005_new_migration,
    "rollback": None  # 可选：回滚函数
})
```

然后实现对应的迁移函数：

```python
async def _migrate_005_new_migration(self):
    """迁移005：新迁移"""
    logger.info("开始执行新迁移...")
    # 迁移逻辑
    return {"result": "success"}
```

## 注意事项

1. **备份数据**: 在生产环境运行迁移前，请先备份数据库
2. **测试环境**: 建议先在测试环境运行迁移，验证无误后再在生产环境执行
3. **迁移顺序**: 迁移按注册顺序执行，确保迁移之间的依赖关系正确
4. **幂等性**: 迁移脚本设计为幂等的，可以安全地多次运行
5. **错误处理**: 如果迁移失败，会在 `migration_history` 中记录错误信息

## 故障排查

### 迁移失败

1. 查看日志输出，了解具体错误信息
2. 检查 `migration_history` 集合中的错误记录
3. 检查数据库连接是否正常
4. 确认数据库权限是否足够

### 索引创建失败

- 检查索引名称是否冲突
- 确认字段是否存在
- 查看MongoDB日志获取详细错误信息

### Neo4j连接失败

- 确认Neo4j服务是否运行
- 检查连接配置（NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD）
- 在Docker环境中，确认网络配置正确
