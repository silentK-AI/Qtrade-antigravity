# Quati-Trade 云端部署操作手册

> 适用环境：腾讯云轻量应用服务器 Windows Server 2022

## 一、远程连接服务器

在你的 Mac 上：
1. 打开 **Microsoft Remote Desktop**（App Store 免费下载）
2. 点 **Add PC** → 输入服务器公网 IP
3. 用购买时设置的管理员账号密码登录

## 二、安装基础环境

登录远程桌面后，**右键开始菜单 → Windows PowerShell (管理员)**，依次执行：

### 2.1 安装 Python
```powershell
# 下载 Python 安装包
Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile "$env:TEMP\python-installer.exe"

# 静默安装（自动加 PATH）
Start-Process -Wait -FilePath "$env:TEMP\python-installer.exe" -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1"
```

### 2.2 安装 Git（用国内镜像）
```powershell
Invoke-WebRequest -Uri "https://registry.npmmirror.com/-/binary/git-for-windows/v2.44.0.windows.1/Git-2.44.0-64-bit.exe" -OutFile "$env:TEMP\git-installer.exe"

Start-Process -Wait -FilePath "$env:TEMP\git-installer.exe" -ArgumentList "/VERYSILENT /NORESTART"
```

### 2.3 ⚠️ 重新打开 PowerShell
**关闭当前窗口，重新打开一个新的 PowerShell (管理员)**，否则 PATH 不生效。

验证安装：
```powershell
python --version
git --version
```

## 三、部署代码

```powershell
# 拉取代码
cd C:\
git clone https://github.com/silentK-AI/Qtrade-antigravity.git Quati-Trade

# 进入项目目录
cd C:\Quati-Trade

# 安装依赖（使用国内镜像加速）
pip install -r deploy\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 四、安装同花顺

1. 打开服务器上的 **Edge 浏览器**
2. 访问 https://activity.ths123.com/acmake/cache/1482.html 下载同花顺
3. 安装完成后 → 打开同花顺 → **手动登录你的国泰海通账户**
4. 确认登录成功，能看到持仓信息

## 五、启动交易系统

### 方式一：手动启动（推荐先用这个测试）
**打开两个 PowerShell 窗口：**

窗口 1 - Dashboard 监控：
```powershell
cd C:\Quati-Trade
python main.py dashboard --port 8088
```

窗口 2 - 实盘交易：
```powershell
cd C:\Quati-Trade
set TRADER_BACKEND=easytrader
python main.py live --etf 513310 513880
```

### 方式二：一键启动（熟悉后使用）
```powershell
cd C:\Quati-Trade
deploy\startup.bat
```

## 六、远程监控

在你的手机或电脑浏览器中访问：
```
http://<服务器公网IP>:8088
```

> ⚠️ 首先需要在腾讯云控制台 → 防火墙 → 添加规则 → 放行 TCP 8088 端口

## 七、断开远程桌面前

**重要！** 断开 RDP 前必须执行，否则 easytrader 的 GUI 自动化会失效：

```powershell
cd C:\Quati-Trade
deploy\keep_session.bat
```
以管理员身份运行，然后再断开远程桌面。

## 八、常见问题

| 问题 | 解决方案 |
|------|----------|
| pip 安装慢 | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 同花顺弹窗 | 设置里关闭自动更新和消息推送 |
| 内存不够 | 关闭 Windows Defender 实时保护、关闭自动更新 |
| Dashboard 外网访问不了 | 检查腾讯云防火墙是否放行 8088 端口 |
| easytrader 连接失败 | 确认同花顺下单客户端（非行情客户端）已打开并登录 |
