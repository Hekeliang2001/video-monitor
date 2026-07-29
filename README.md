# Playwright URL 打开与视频状态监测工具

一个基于 Python Playwright 的轻量 CLI 工具，用于打开指定 URL，并在控制台中动态显示页面里的 `video` 播放状态。

默认模式只读取视频状态，不会自动播放、不点击页面、不修改播放器行为。

如果显式启用 `--auto-play`，工具会在动态检测到 `video` 元素时尝试调用浏览器原生的 `video.play()` 播放视频。

## 安装

Windows 可以直接双击 `install_windows.bat` 安装依赖，再双击 `start_windows.bat` 启动控制台。如果需要生成 exe，在 Windows 上双击 `build_windows_exe.bat` 或 `build_windows_standalone_exe.bat`。如果没有 Windows 环境，可以使用内置的 GitHub Actions 配置云端生成 `VideoMonitorConsole.exe` 和 `VideoMonitorConsoleSetup.exe` 安装包。脚本不会下载 Playwright 自带 Chromium，运行时使用系统已安装的 Edge 或 Chrome，默认 Edge。如果电脑没有 Python，脚本会自动下载本地构建用 Python。想避免占用 C 盘，请先把整个项目文件夹放到 D 盘、E 盘或移动硬盘后再运行脚本。详细说明见 `README_WINDOWS.md`。

macOS / Linux 可以使用：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用

启动本地功能页面：

```bash
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

页面支持配置课程 URL、手机号、密码、自动登录、浏览器、自动播放、顺序播放、静音播放、二倍速、下一节按钮选择器、无视频等待时间、Bark 手机提醒，并实时显示运行日志。运行后可以在页面里暂停、继续或停止任务，也可以导出日志、测试 Bark 推送、将常用配置保存到本地浏览器。

启用“自动登录”后，工具会在打开课程链接后自动识别手机号/密码登录页，填写控制台中的手机号和密码并点击登录。密码只通过本地后端环境变量传给 Playwright，不会显示在命令预览和日志命令里。保存配置时，密码只有在勾选“记住密码”后才会保存到本地浏览器。

Bark 提醒可以填写 Bark Key，也可以填写完整的 `https://api.day.app/你的Key`。启用“每节完成提醒”后，每个视频播放完成都会推送一次；启用“全部完成提醒”后，当前页面视频全部看完但没有可点击下一节时会推送。可以先点击“测试推送”确认手机可收到提醒。Bark Key 通过本地后端环境变量传给 Playwright，不会显示在命令预览和日志命令里。

也可以继续直接使用命令行：

```bash
python main.py --url 'https://example.com'
```

如果 URL 里包含 `&`，必须用英文引号包起来：

```bash
python main.py --url 'https://example.com?a=1&b=2'
```

默认会打开系统已安装的 Microsoft Edge，并持续监测当前页面和 iframe 里的 `video` 标签。

关闭方式：

```text
回到终端按 Enter
```

也可以用 `Ctrl+C` 结束。

如果本机安装了 Google Chrome，可以指定 Chrome 通道：

```bash
python main.py --url 'https://example.com' --browser-channel chrome
```

如果想显式使用 Microsoft Edge：

```bash
python main.py --url 'https://example.com' --browser-channel msedge
```

调整监测间隔：

```bash
python main.py --url 'https://example.com' --monitor-interval 1
```

动态检测到视频后自动播放：

```bash
python main.py --url 'https://example.com' --auto-play
```

如果浏览器因为自动播放策略拦截播放，可以先静音再自动播放：

```bash
python main.py --url 'https://example.com' --auto-play --mute-before-auto-play
```

如果需要等当前视频播放完成后再自动播放下一个视频：

```bash
python main.py --url 'https://example.com' --auto-play --play-sequential
```

顺序播放也可以和静音自动播放一起使用：

```bash
python main.py --url 'https://example.com' --auto-play --play-sequential --mute-before-auto-play
```

如果当前视频播放完成后需要自动进入下一节，可以指定“下一节”按钮的 CSS 选择器：

```bash
python main.py --url 'https://example.com' --auto-play --play-sequential --mute-before-auto-play --next-selector '#prevNextFocusNext'
```

指定 `--next-selector` 后，如果页面没有检测到视频，也会在短暂等待后点击下一节按钮。默认等待 3 秒，可以调整：

```bash
python main.py --url 'https://example.com' --auto-play --play-sequential --mute-before-auto-play --next-selector '#prevNextFocusNext' --no-video-next-delay 1
```

将检测到的视频自动切换为二倍速：

```bash
python main.py --url 'https://example.com' --auto-play --play-sequential --mute-before-auto-play --next-selector '#prevNextFocusNext' --playback-rate 2
```

命令行自动登录需要用环境变量传入手机号和密码：

```bash
VIDEO_MONITOR_LOGIN_PHONE='手机号' VIDEO_MONITOR_LOGIN_PASSWORD='密码' python main.py --url 'https://example.com' --auto-login --auto-play --play-sequential --mute-before-auto-play --next-selector '#prevNextFocusNext' --playback-rate 2
```

商业用途请确保你拥有对应内容的播放、展示和使用权限，并符合目标网站或平台的使用条款。

## 功能

- 打开指定 URL
- 提供本地功能页面配置参数、启动/停止任务、查看实时日志
- 支持一键导出运行日志
- 支持保存/清除本地配置，刷新页面后自动恢复常用参数
- 提供暂停/继续按钮，暂停时会暂停当前视频并暂停自动化动作
- 可选：遇到手机号/密码登录页时自动登录
- 可选：通过 Bark 在每节完成或全部完成时推送手机提醒，并支持测试推送
- 动态扫描页面和 iframe 中的 `video` 标签
- 在控制台显示播放状态、当前进度、总时长、音量、倍速、可见尺寸、视频地址等信息
- 可选：动态检测到视频后自动播放
- 可选：顺序自动播放，当前视频结束后再播放下一个视频
- 可选：当前页面视频全部播放完成后，点击指定的下一节按钮
- 可选：当前页面没有视频且存在下一节按钮时，点击指定的下一节按钮
- 可选：使用视频原生 `playbackRate` 自动切换播放倍速
- 可选：自动播放前静音，以提高被浏览器允许播放的概率
- 可选择 Chrome / Edge 通道
- 不分析 DOM
- 不监听网络请求
- 不生成报告文件
- 默认不自动播放视频
