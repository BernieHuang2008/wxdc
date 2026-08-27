"""
ws-scrcpy Python 控制客户端
通过 WebSocket 直接与 ws-scrcpy 通信，实现 Android 设备远程控制
基于 scrcpy 二进制控制协议实现
"""

import asyncio
import struct
import base64
import subprocess
from typing import Optional, Tuple
from dataclasses import dataclass
from PIL import Image
from io import BytesIO
import websockets


# ==================== 协议常量 ====================
# 参考: https://github.com/NetrisTV/ws-scrcpy/blob/master/src/app/controlMessage/ControlMessage.ts
class ControlMessageType:
    TYPE_KEYCODE = 0
    TYPE_TEXT = 1
    TYPE_TOUCH = 2
    TYPE_SCROLL = 3
    TYPE_BACK_OR_SCREEN_ON = 4
    TYPE_EXPAND_NOTIFICATION_PANEL = 5
    TYPE_EXPAND_SETTINGS_PANEL = 6
    TYPE_COLLAPSE_PANELS = 7
    TYPE_GET_CLIPBOARD = 8
    TYPE_SET_CLIPBOARD = 9
    TYPE_SET_SCREEN_POWER_MODE = 10
    TYPE_ROTATE_DEVICE = 11


# 触摸动作常量 (参考 Android MotionEvent)
class TouchAction:
    ACTION_DOWN = 0
    ACTION_UP = 1
    ACTION_MOVE = 2
    ACTION_CANCEL = 3


# 按键动作常量 (参考 Android KeyEvent)
class KeyAction:
    ACTION_DOWN = 0
    ACTION_UP = 1
    ACTION_BOTH = 2  # scrcpy 同时发送 DOWN 和 UP


# 屏幕电源模式
class PowerMode:
    OFF = 0
    ON = 1


# 常用 Android KeyCode
class KeyCode:
    KEYCODE_HOME = 3
    KEYCODE_BACK = 4
    KEYCODE_CALL = 5
    KEYCODE_ENDCALL = 6
    KEYCODE_VOLUME_UP = 24
    KEYCODE_VOLUME_DOWN = 25
    KEYCODE_POWER = 26
    KEYCODE_CAMERA = 27
    KEYCODE_CLEAR = 28
    KEYCODE_ENTER = 66
    KEYCODE_DEL = 67
    KEYCODE_MENU = 82
    KEYCODE_SEARCH = 84
    KEYCODE_APP_SWITCH = 187


@dataclass
class Point:
    """屏幕坐标点"""
    x: int
    y: int


@dataclass
class ScreenSize:
    """屏幕尺寸"""
    width: int
    height: int


# ==================== 核心客户端 ====================

class WsScrcpyClient:
    """
    ws-scrcpy Python 客户端
    通过 WebSocket 与 ws-scrcpy 服务通信，控制 Android 设备
    """

    def __init__(self, ws_url: str, serial: Optional[str] = None):
        """
        初始化客户端
        
        Args:
            ws_url: WebSocket URL，例如 ws://localhost:5039/scrcpy
            serial: 设备序列号，如果 ws-scrcpy 只连接了一个设备可以为 None
        """
        self.ws_url = ws_url
        self.serial = serial
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._screen_size: Optional[ScreenSize] = None

    # ==================== 连接管理 ====================

    async def connect(self):
        """建立 WebSocket 连接"""
        self.websocket = await websockets.connect(self.ws_url)
        print(f"✅ 已连接到 {self.ws_url}")

    async def disconnect(self):
        """关闭 WebSocket 连接"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            print("🔌 连接已关闭")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    # ==================== 核心控制方法 ====================

    async def _send_binary(self, data: bytes):
        """发送二进制控制消息"""
        if not self.websocket:
            raise Exception("未连接到服务器，请先调用 connect()")
        await self.websocket.send(data)

    async def tap(self, x: int, y: int, pointer_id: int = 0):
        """
        点击屏幕指定位置
        
        参考: TouchControlMessage.toBuffer()
        https://github.com/NetrisTV/ws-scrcpy/blob/master/src/app/controlMessage/TouchControlMessage.ts#L21-L31
        """
        # 获取屏幕尺寸用于归一化
        if not self._screen_size:
            await self._get_screen_size()

        # TouchControlMessage 格式 (28字节 payload + 1字节 type)
        # 参考: https://deepwiki.com/Genymobile/scrcpy/2.8-control-message-protocol
        # 结构: type(1) + action(1) + pointerId(4) + x(4) + y(4) + screenWidth(2) + screenHeight(2) + pressure(2) + buttons(4)
        # 总长度: 1 + 28 = 29 字节

        # 压力值归一化 (0~1 映射到 0~0xffff)
        MAX_PRESSURE = 0xffff

        # 构造消息
        msg = bytearray(29)
        offset = 0

        # type: 2 (触摸事件)
        msg[offset] = ControlMessageType.TYPE_TOUCH
        offset += 1

        # action: 按下 (0)
        msg[offset] = TouchAction.ACTION_DOWN
        offset += 1

        # pointerId: 4字节大端
        struct.pack_into('>I', msg, offset, pointer_id)
        offset += 4

        # x: 4字节大端
        struct.pack_into('>I', msg, offset, x)
        offset += 4

        # y: 4字节大端
        struct.pack_into('>I', msg, offset, y)
        offset += 4

        # screenWidth: 2字节大端
        struct.pack_into('>H', msg, offset, self._screen_size.width)
        offset += 2

        # screenHeight: 2字节大端
        struct.pack_into('>H', msg, offset, self._screen_size.height)
        offset += 2

        # pressure: 2字节大端 (归一化)
        struct.pack_into('>H', msg, offset, MAX_PRESSURE)
        offset += 2

        # buttons: 4字节大端 (0)
        struct.pack_into('>I', msg, offset, 0)

        # 发送按下事件
        await self._send_binary(bytes(msg))

        # 发送抬起事件 (修改 action 为 1)
        msg[1] = TouchAction.ACTION_UP
        await self._send_binary(bytes(msg))

    async def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int,
                    duration_ms: int = 300, steps: int = 20):
        """
        滑动操作：从起点滑到终点
        
        Args:
            start_x, start_y: 起点坐标
            end_x, end_y: 终点坐标
            duration_ms: 滑动持续时间（毫秒）
            steps: 插值步数
        """
        if not self._screen_size:
            await self._get_screen_size()

        MAX_PRESSURE = 0xffff

        # 计算每步的增量
        step_delay = duration_ms / steps
        dx = (end_x - start_x) / steps
        dy = (end_y - start_y) / steps

        # 按下
        await self._send_touch_event(TouchAction.ACTION_DOWN, start_x, start_y, MAX_PRESSURE)

        # 移动
        for i in range(1, steps + 1):
            x = int(start_x + dx * i)
            y = int(start_y + dy * i)
            await self._send_touch_event(TouchAction.ACTION_MOVE, x, y, MAX_PRESSURE)
            await asyncio.sleep(step_delay / 1000)

        # 抬起
        await self._send_touch_event(TouchAction.ACTION_UP, end_x, end_y, 0)

    async def _send_touch_event(self, action: int, x: int, y: int, pressure: int):
        """发送单个触摸事件 (内部方法)"""
        msg = bytearray(29)
        offset = 0

        msg[offset] = ControlMessageType.TYPE_TOUCH
        offset += 1

        msg[offset] = action
        offset += 1

        struct.pack_into('>I', msg, offset, 0)
        offset += 4

        struct.pack_into('>I', msg, offset, x)
        offset += 4

        struct.pack_into('>I', msg, offset, y)
        offset += 4

        struct.pack_into('>H', msg, offset, self._screen_size.width)
        offset += 2

        struct.pack_into('>H', msg, offset, self._screen_size.height)
        offset += 2

        struct.pack_into('>H', msg, offset, pressure)
        offset += 2

        struct.pack_into('>I', msg, offset, 0)

        await self._send_binary(bytes(msg))

    async def press_key(self, keycode: int, action: int = KeyAction.ACTION_BOTH):
        """
        按下按键
        
        参考: KeyCodeControlMessage.toBuffer()
        https://github.com/NetrisTV/ws-scrcpy/blob/master/src/app/controlMessage/KeyCodeControlMessage.ts#L10-L16
        
        Args:
            keycode: Android KeyCode (如 KeyCode.KEYCODE_HOME)
            action: KeyAction.ACTION_DOWN, ACTION_UP, 或 ACTION_BOTH
        """
        # KeyCodeControlMessage 格式: type(1) + action(1) + keycode(4) + repeat(4) + metaState(4)
        # 总长度: 1 + 13 = 14 字节
        msg = bytearray(14)
        offset = 0

        msg[offset] = ControlMessageType.TYPE_KEYCODE
        offset += 1

        msg[offset] = action
        offset += 1

        struct.pack_into('>I', msg, offset, keycode)
        offset += 4

        struct.pack_into('>I', msg, offset, 0)  # repeat
        offset += 4

        struct.pack_into('>I', msg, offset, 0)  # metaState

        await self._send_binary(bytes(msg))

    async def send_text(self, text: str):
        """
        发送文本 (支持中文)
        
        参考: TextControlMessage.toBuffer()
        https://github.com/NetrisTV/ws-scrcpy/blob/master/src/app/controlMessage/TextControlMessage.ts#L9-L13
        
        注意: scrcpy 的文本注入通过模拟按键实现，对中文支持有限。
        对于中文，建议结合 ADBKeyboard 或使用 ADB broadcast 方式。
        """
        # 方法1: 尝试使用 scrcpy 原生文本注入 (仅支持 ASCII)
        try:
            text_ascii = text.encode('ascii')
            await self._send_text_scrcpy(text)
            return
        except UnicodeEncodeError:
            pass

        # 方法2: 使用 ADB broadcast 方式 (支持中文，需要设备上安装 ADBKeyboard 或类似应用)
        print(f"⚠️ scrcpy 原生文本注入不支持中文，使用 ADB 方式发送: {text}")
        await self._send_text_adb(text)

    async def _send_text_scrcpy(self, text: str):
        """使用 scrcpy 原生协议发送文本 (仅 ASCII)"""
        text_bytes = text.encode('utf-8')
        # TextControlMessage 格式: type(1) + length(4) + text
        msg = bytearray(1 + 4 + len(text_bytes))
        offset = 0

        msg[offset] = ControlMessageType.TYPE_TEXT
        offset += 1

        struct.pack_into('>I', msg, offset, len(text_bytes))
        offset += 4

        msg[offset:] = text_bytes

        await self._send_binary(bytes(msg))

    async def _send_text_adb(self, text: str):
        """通过 ADB 发送文本 (支持中文)"""
        # 使用 ADB 的 broadcast 方式，需要设备上有接收 ADB_INPUT_TEXT 广播的应用
        # 如 ADBKeyboard: https://github.com/senzhk/ADBInputMethod
        if self.serial:
            cmd = ["adb", "-s", self.serial, "shell", "am", "broadcast",
                   "-a", "ADB_INPUT_TEXT", "--es", "msg", text]
        else:
            cmd = ["adb", "shell", "am", "broadcast",
                   "-a", "ADB_INPUT_TEXT", "--es", "msg", text]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # 备用方案: 使用 input text (仅 ASCII)
            print("⚠️ ADB broadcast 失败，尝试使用 input text...")
            if self.serial:
                cmd = ["adb", "-s", self.serial, "shell", "input", "text", text]
            else:
                cmd = ["adb", "shell", "input", "text", text]
            subprocess.run(cmd, capture_output=True, text=True)

    async def back(self):
        """按下返回键"""
        await self.press_key(KeyCode.KEYCODE_BACK)

    async def home(self):
        """按下 Home 键"""
        await self.press_key(KeyCode.KEYCODE_HOME)

    async def recent_apps(self):
        """按下最近任务键"""
        await self.press_key(KeyCode.KEYCODE_APP_SWITCH)

    async def set_screen_power_mode(self, mode: int):
        """
        设置屏幕电源模式
        
        参考: https://github.com/NetrisTV/ws-scrcpy/blob/master/src/app/controlMessage/CommandControlMessage.ts
        """
        msg = bytearray(2)
        msg[0] = ControlMessageType.TYPE_SET_SCREEN_POWER_MODE
        msg[1] = mode
        await self._send_binary(bytes(msg))

    async def turn_screen_off(self):
        """关闭屏幕"""
        await self.set_screen_power_mode(PowerMode.OFF)

    async def turn_screen_on(self):
        """打开屏幕"""
        await self.set_screen_power_mode(PowerMode.ON)

    async def rotate_device(self):
        """旋转设备屏幕"""
        msg = bytearray(1)
        msg[0] = ControlMessageType.TYPE_ROTATE_DEVICE
        await self._send_binary(bytes(msg))

    async def expand_notification_panel(self):
        """展开通知面板"""
        msg = bytearray(1)
        msg[0] = ControlMessageType.TYPE_EXPAND_NOTIFICATION_PANEL
        await self._send_binary(bytes(msg))

    async def expand_settings_panel(self):
        """展开快捷设置面板"""
        msg = bytearray(1)
        msg[0] = ControlMessageType.TYPE_EXPAND_SETTINGS_PANEL
        await self._send_binary(bytes(msg))

    async def collapse_panels(self):
        """收起所有面板"""
        msg = bytearray(1)
        msg[0] = ControlMessageType.TYPE_COLLAPSE_PANELS
        await self._send_binary(bytes(msg))

    # ==================== 屏幕截图 ====================

    async def _get_screen_size(self):
        """获取屏幕尺寸 (通过 ADB)"""
        self._screen_size = ScreenSize(1080, 1920)
        
        try:
            if self.serial:
                cmd = ["adb", "-s", self.serial, "shell", "wm", "size"]
            else:
                cmd = ["adb", "shell", "wm", "size"]

            result = subprocess.run(cmd, capture_output=True, text=True)
            output = result.stdout.strip()
            # 输出格式: "Physical size: 1080x1920" 或 "1080x1920"
            import re
            match = re.search(r'(\d+)x(\d+)', output)
            if match:
                self._screen_size = ScreenSize(int(match.group(1)), int(match.group(2)))
                print(f"📱 屏幕尺寸: {self._screen_size.width}x{self._screen_size.height}")
            else:
                # 默认值
                self._screen_size = ScreenSize(1080, 1920)
        except Exception as e:
            print(f"⚠️ 获取屏幕尺寸失败: {e}")
            self._screen_size = ScreenSize(1080, 1920)

    async def screenshot(self) -> Image.Image:
        """
        获取屏幕截图 (通过 ADB)
        
        Returns:
            PIL.Image 对象
        """
        try:
            if self.serial:
                cmd = ["adb", "-s", self.serial, "exec-out", "screencap", "-p"]
            else:
                cmd = ["adb", "exec-out", "screencap", "-p"]

            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0:
                img = Image.open(BytesIO(result.stdout))
                print(f"📸 截图成功: {img.size[0]}x{img.size[1]}")
                return img
            else:
                raise Exception(f"截图失败: {result.stderr.decode()}")
        except Exception as e:
            raise Exception(f"截图失败: {e}")

    async def screenshot_base64(self) -> str:
        """获取屏幕截图 (Base64 编码)"""
        img = await self.screenshot()
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')


# ==================== 使用示例 ====================

async def main():
    # 配置
    WS_URL = "ws://192.168.1.7:5039/scrcpy"  # 替换为你的 ws-scrcpy 地址
    SERIAL = "WJX7N17731000362"  # 如果有多个设备，指定序列号

    async with WsScrcpyClient(WS_URL, SERIAL) as client:
        print("🚀 开始控制设备...")

        # 1. 获取屏幕尺寸
        await client._get_screen_size()

        # 2. 点击屏幕中央
        await client.tap(540, 960)
        await asyncio.sleep(0.5)

        # 3. 滑动 (从底部向上滑)
        await client.swipe(540, 1800, 540, 300, duration_ms=500)
        await asyncio.sleep(1)

        # 4. 发送文本
        await client.send_text("你好，世界！")
        await asyncio.sleep(1)

        # 5. 按下 Home 键
        await client.home()
        await asyncio.sleep(0.5)

        # 6. 截图
        img = await client.screenshot()
        img.save("screenshot.png")
        print("💾 截图已保存为 screenshot.png")

        # 7. 关闭屏幕
        await client.turn_screen_off()


if __name__ == "__main__":
    asyncio.run(main())