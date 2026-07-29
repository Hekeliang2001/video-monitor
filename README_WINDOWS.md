# Windows 使用说明

## 运行环境

- Windows 10 或 Windows 11
- Microsoft Edge 或 Google Chrome
- 网络可访问 Python 官网和 Python 包源

脚本会优先使用电脑上已有的 Python 3；如果没有检测到 Python，会自动下载一个本地构建用 Python 到当前目录的 `.build-python` 文件夹，不需要手动安装到系统 PATH。临时下载文件和 pip 缓存也会尽量放在当前目录下，方便整体删除。

默认使用系统自带的 Microsoft Edge；也可以在控制台里切换为 Google Chrome。脚本不会下载 Playwright 自带 Chromium。

## 首次安装

解压本目录后，双击：

```text
install_windows.bat
```

这个脚本会自动完成：

- 检测 Python；没有 Python 时自动下载本地构建用 Python
- 创建 `.venv` 虚拟环境
- 安装 `requirements.txt` 中的依赖
- 使用系统已安装的 Edge 或 Chrome

## 启动控制台

安装完成后，双击：

```text
start_windows.bat
```

浏览器会自动打开：

```text
http://127.0.0.1:8000/
```

如果 8000 端口被占用或被 Windows 拦截，程序会自动切换到其他可用端口，并在黑色命令行窗口里显示新的地址，例如：

```text
Port 8000 is unavailable; using port 8001.
Video Monitor Console: http://127.0.0.1:8001/
```

使用时请保持启动脚本的命令行窗口打开。关闭窗口或按 `Ctrl+C` 会停止本地控制台服务。

## 文件存储位置

如果把项目解压到 `D:\video-monitor-windows`，构建相关文件会优先保存在：

```text
D:\video-monitor-windows\.build-python\
D:\video-monitor-windows\.venv\
D:\video-monitor-windows\.pip-cache\
D:\video-monitor-windows\.temp\
D:\video-monitor-windows\build\
D:\video-monitor-windows\dist\
```

最终程序是：

```text
D:\video-monitor-windows\dist\VideoMonitorConsole.exe
```

如果你把项目解压到 C 盘，那这些文件自然也会在 C 盘的项目目录里。想避免占用 C 盘，请先把整个文件夹放到 D 盘、E 盘或移动硬盘后再运行构建脚本。

## 构建轻量 EXE

如果只需要把 Python 代码和依赖打进 exe，请在 Windows 电脑上双击：

```text
build_windows_exe.bat
```

完成后会生成：

```text
dist\VideoMonitorConsole.exe
```

之后可以直接双击 `dist\VideoMonitorConsole.exe` 启动控制台，也可以双击：

```text
start_exe_windows.bat
```

注意：Windows exe 需要在 Windows 系统上构建。macOS 不能稳定直接生成可运行的 Windows `.exe`。

构建脚本会检测 Python；没有 Python 时自动下载本地构建用 Python，然后安装 Python 依赖和 PyInstaller。不会下载 Playwright Chromium。生成的 exe 使用系统已安装的 Edge 或 Chrome。

## 构建单文件 EXE

如果想生成单个 exe，也可以继续双击：

```text
build_windows_standalone_exe.bat
```

完成后同样会生成：

```text
dist\VideoMonitorConsole.exe
```

这个 exe 会整合 Python 依赖和网页控制台，但不会整合浏览器。注意事项：

- 运行电脑需要有 Microsoft Edge 或 Google Chrome。
- 第一次启动可能更慢，因为单文件 exe 会先解压内置运行环境。
- 构建时仍然需要 Windows 电脑联网下载本地构建用 Python 和 Python 包。
- 如果构建时报路径过长，可以把项目放到较短路径，例如 `C:\video-monitor` 后再运行脚本。

## 没有 Windows 环境时构建安装包

如果你手边没有 Windows，可以用 GitHub Actions 的 Windows 云端环境构建：

1. 在 GitHub 新建一个仓库。
2. 把本项目里的文件上传到仓库根目录，确保包含 `.github\workflows\build-windows-installer.yml` 和 `VideoMonitorConsole.iss`。
3. 打开仓库的 `Actions` 页面。
4. 选择 `Build Windows Installer`。
5. 点击 `Run workflow`。
6. 等构建完成后，下载 `VideoMonitorConsole-Windows` 构建产物。

构建产物里会包含：

```text
VideoMonitorConsole.exe
VideoMonitorConsoleSetup.exe
README_WINDOWS.md
```

其中 `VideoMonitorConsoleSetup.exe` 是 Windows 安装包，双击后会安装程序并创建开始菜单快捷方式。这个安装包同样不会内置 Chromium，目标电脑需要有 Microsoft Edge 或 Google Chrome。

## 修改端口

如果 `8000` 端口被占用，可以在命令行里这样启动：

```bat
start_windows.bat 8080
```

然后打开：

```text
http://127.0.0.1:8080/
```

新版程序也会自动避开不可用端口。如果浏览器页面打不开，请以黑色命令行窗口里打印的 `Video Monitor Console: ...` 地址为准。

## 手机访问说明

`127.0.0.1` 只代表当前这台电脑。手机上直接打开 `http://127.0.0.1:8000/` 不会访问到电脑。

如果后续需要让手机访问控制台，需要改成局域网监听方式，并使用电脑的局域网 IP。

## 隐私说明

压缩包不会包含你的手机号、密码、Bark Key、浏览器缓存或运行记录。

网页里的“保存配置”使用浏览器本地存储。密码只有在勾选“记住密码”后才会保存到当前浏览器。
