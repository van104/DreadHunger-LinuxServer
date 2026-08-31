Dread Hunger Linux 独立管理器
============================

此管理器不加载 Windows 开服器、run.pyc、DreadHunger.pyd 或卡密模块。
它直接管理 LinuxServer 自带的 ELF 服务器。

快速启动
--------

    python3 DreadHungerLinuxManager.pyz --root "$(pwd)"

或：

    chmod +x DreadHungerLinuxManager.sh
    ./DreadHungerLinuxManager.sh

默认面板地址：

    http://127.0.0.1:8800

远程管理建议使用 SSH 隧道，不要直接暴露面板：

    ssh -L 8800:127.0.0.1:8800 user@server

Windows 图形客户端：

    WindowsRemote/dist/DreadHungerLinuxRemoteManager.exe

客户端中填写服务器 IP（或域名）、管理端口和 --password 设置的密码即可连接。
若使用上面的 SSH 隧道，客户端地址填写 127.0.0.1，端口填写 8800。

检查文件：

    python3 DreadHungerLinuxManager.pyz --root "$(pwd)" --check

需要无 Python 依赖的 Linux ELF 时，在 Linux 上执行：

    chmod +x build_linux_manager.sh
    ./build_linux_manager.sh

输出文件：`dist/DreadHungerLinuxManager`

首次保存配置后生成 manager_config.json。服务器日志写入 manager_logs，原始游戏日志只读显示。
启动、停止、重启操作只管理本程序启动的服务器进程组。
