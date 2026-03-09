---
description: 将代码部署到云端服务器的标准流程
---

# 代码部署到服务器的标准流程

每次有代码改动需要同步到服务器时，**必须按以下步骤执行**：

## 1. 提交代码
```bash
git add <files>
git commit -m "<commit message>"
```

## 2. 双推到 GitHub + Gitee
// turbo
```bash
git push
```
> `origin` 已配置双 push URL（GitHub + Gitee），一条命令自动推送两边。

## 3. 通知用户在服务器上拉取
告诉用户在服务器 PowerShell 中执行：
```powershell
cd C:\Quati-Trade
git pull gitee main
```

## ⚠️ 注意事项
- **禁止**使用其他方式上传代码到服务器（如 scp、手动复制等）
- 服务器从 **Gitee** 拉取（国内速度快）
- 本地同时推 **GitHub + Gitee**
- 服务器地址: `115.159.33.219`（腾讯云 Windows Server）
