# DSH Plugin Index

DSH 插件市场索引（格式 1）——社区精选 Top 80，供 DSH 桌面端「索引源」使用。

## 使用

在 DSH 桌面端「插件 → 发现 → + 添加索引源」填入：

```
https://cdn.jsdelivr.net/gh/stellvyr/dsh-plugin-index@main/plugins.json
```

## 说明

- 格式：DSH 官方 `dsh-plugin-market-index` 格式 1（顶层 `format: 1`）
- 插件：按 star 精选的 80 个真实 DSH 插件，中英双语描述
- 安装：Git source 锁定真实 commit SHA（`git+https://...#<commit>`）
- 数据源：dsh.market 目录（2026-10-17 快照）
- 版本号 0.1.0 为展示占位，安装以 commit 锁定为准
- 更新：重新生成 plugins.json 推送到本仓库即可
