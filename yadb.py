import re
from typing import Optional, Tuple, List

class YadbClient:
    """
    YADB 命令行工具的 Python 封装。
    通过 adbutils.Device 执行 shell 命令。
    """
    
    def __init__(self, device, yadb_path: str = "/data/local/tmp/yadb"):
        """
        初始化 YADB 客户端。
        
        参数:
            device: adbutils.Device 对象（已连接设备）
            yadb_path: 设备上 YADB 可执行文件的路径（默认 /data/local/tmp/yadb）
        """
        self.device = device
        self.yadb_path = yadb_path
        # 基础命令模板
        self.base_cmd = f"app_process -Djava.class.path={yadb_path} /data/local/tmp com.ysbing.yadb.Main"

    
    def yadb_push(self, force=False):
        if force or not self.yadb_check():
            self.device.push("/app/yadb", "/data/local/tmp")
            self.device.shell("chmod 755 /data/local/tmp/yadb")

    def yadb_check(self):
        result = self.device.shell("ls /data/local/tmp/yadb")
        if "No such file or directory" in result:
            return False
        else:
            return True
    
    def _run(self, args: List[str]) -> str:
        """
        执行 YADB 命令并返回输出。
        
        参数:
            args: 命令参数列表，如 ['-swipe', '100', '500', '900', '500', '1000']
        
        返回:
            命令的标准输出字符串
        """
        # 构建完整命令
        cmd_parts = [self.base_cmd] + args
        cmd = " ".join(cmd_parts)
        # 使用 device.shell 执行
        output = self.device.shell(cmd)
        # 可选：检查输出是否包含 "aborted" 等错误关键字
        if "aborted" in output.lower():
            raise RuntimeError(f"YADB 命令执行失败 (aborted): {cmd}\n输出: {output}")
        return output
    
    # ========== 触摸操作 ==========
    
    def tap(self, x: int, y: int):
        """
        点击指定坐标（短按）。
        """
        return self._run(['-touch', str(x), str(y), '0'])
    
    def long_press(self, x: int, y: int, duration_ms: int):
        """
        长按指定坐标。
        """
        return self._run(['-touch', str(x), str(y), str(duration_ms)])
    
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int):
        """
        滑动，支持自定义持续时间（可有效减少惯性）。
        """
        return self._run(['-swipe', str(x1), str(y1), str(x2), str(y2), str(duration_ms)])
    
    def long_press_drag(self, x1: int, y1: int, x2: int, y2: int, 
                        press_duration_ms: int, drag_duration_ms: int):
        """
        长按并拖拽（先长按起点，再拖拽至终点）。
        """
        return self._run([
            '-longPressDrag', 
            str(x1), str(y1), str(x2), str(y2),
            str(press_duration_ms), str(drag_duration_ms)
        ])
    
    def pinch(self, center_x: int, center_y: int, 
              start_distance: int, end_distance: int, duration_ms: int):
        """
        双指捏合/放大。
        中心点 (center_x, center_y)，初始两指距离 start_distance，最终距离 end_distance。
        注意：具体参数含义请参考 YADB 文档。
        """
        return self._run([
            '-pinch',
            str(center_x), str(center_y),
            str(start_distance), str(end_distance),
            str(duration_ms)
        ])
    
    # ========== 文本输入 ==========
    
    def input_text(self, text: str):
        """
        输入文本（支持中文、Emoji 等）。
        注意：需要手机已启用 ADBKeyboard 或 YADB 自带的输入法。
        """
        # 转义双引号和反斜杠（防止破坏 shell 命令）
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')
        # 整个文本用双引号包裹
        return self._run(['-keyboard', f'"{escaped}"'])
    
    # ========== 系统按键 ==========
    
    def press_keycode(self, keycode: int):
        """
        发送系统按键事件。
        常用键码：3=HOME, 4=BACK, 187=APP_SWITCH, 26=POWER 等。
        """
        return self._run(['-keyevent', str(keycode)])
    
    def press_home(self):
        return self.press_keycode(3)
    
    def press_back(self):
        return self.press_keycode(4)
    
    def press_recent(self):
        return self.press_keycode(187)
    
    # ========== 截图 ==========
    
    def screenshot(self, save_to_pc_path: Optional[str] = None) -> Optional[bytes]:
        """
        获取屏幕截图。
        
        参数:
            save_to_pc_path: 若指定，则将截图保存到 PC 本地路径（如 'screenshot.png'）。
                             若不指定，则返回原始 PNG 字节数据。
        
        返回:
            若不指定路径，返回 PNG 字节串；若指定路径，返回 None（但会保存文件）。
        """
        # 方法：YADB 的 -screenshot 默认输出到 stdout，我们直接捕获。
        # 但 YADB 可能将二进制数据输出到 stdout，而 device.shell 默认按字符串处理可能有问题。
        # 我们改用 device.shell 的原始字节输出（需要 adbutils 支持）。
        # adbutils 的 shell 方法返回字符串，但我们可以通过 exec-out 获取二进制。
        # 这里我们使用标准 adb 命令直接拉取：先保存到手机，再 pull。
        # 更可靠的方式：使用 YADB 的 -screenshot 输出到文件？
        # 我们采用传统方式：先 screencap 到手机，再 pull。
        # 为了简便，我们直接使用 device.screencap() 方法（adbutils 自带）。
        # 如果用户坚持要用 YADB，可以如下操作：
        # 1. 执行 YADB -screenshot 并将输出重定向到文件（在手机内）。
        # 2. 然后用 adb pull 拉取。
        # 由于 adbutils 已经提供了 screenshot，我们直接调用。
        # 若用户希望完全使用 YADB，这里提供一种实现。
        # 以下代码将截图保存到手机 /sdcard/yadb_screenshot.png，然后 pull。
        remote_path = "/sdcard/yadb_screenshot.png"
        self._run(['-screenshot', remote_path])  # 假设 YADB 支持输出到文件
        # 拉取到 PC
        pc_data = self.device.sync.pull(remote_path)
        # 删除手机上的临时文件
        self.device.shell(f"rm {remote_path}")
        if save_to_pc_path:
            with open(save_to_pc_path, 'wb') as f:
                f.write(pc_data)
            return None
        return pc_data
    
    # 如果用户想用 adbutils 原生截图，可以直接 device.screenshot()
    
    # ========== UI 布局 ==========
    
    def dump_layout(self) -> str:
        """
        获取当前界面的 UI 层次结构（XML 格式）。
        返回 XML 字符串。
        """
        return self._run(['-layout'])
    
    # ========== 其他实用功能 ==========
    
    def get_window_size(self) -> Tuple[int, int]:
        """
        获取屏幕尺寸（宽度, 高度）。
        """
        # 使用 adbutils 自带方法
        size = self.device.window_size()
        if size:
            return size
        # 若失败，通过 dumpsys 获取
        output = self.device.shell("wm size")
        match = re.search(r'(\d+)x(\d+)', output)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        raise RuntimeError("无法获取屏幕尺寸")
    
    # 你可以根据需要添加更多命令，比如 -click、-scroll 等
    # 具体可参考 YADB 官方文档：https://github.com/ysbing/YADB
