import os
import json
from typing import Dict, List, Optional

class PomPovEditor:
    def __init__(self):
        # 1. 内存管理：编辑器自建 P 开头内存（key=补位后地址，value=数值）
        self.editor_memory: Dict[str, int] = {}
        # 2. 磁盘地址映射：C:/D:/ 开头对应系统合法路径（存储配置文件）
        self.disk_map = {
            "C:": os.path.join(os.getenv("LOCALAPPDATA", "."), "PomPovEditor", "C_drive"),
            "D:": os.path.join(os.getenv("LOCALAPPDATA", "."), "PomPovEditor", "D_drive")
        }
        # 3. 核心配置（按你的规则）
        self.cxba_bits = 2  # cxba=补2位
        self.loop_running = False  # 循环状态
        self.terminate_constant = 0  # 循环终止常量（C3113941521）

    def _init_disk(self):
        """初始化磁盘目录（确保合法路径存在）"""
        for path in self.disk_map.values():
            if not os.path.exists(path):
                os.makedirs(path)

    def _pad_address(self, addr: str) -> str:
        """地址补2位（仅对 P 开头地址生效）"""
        if addr.startswith("P"):
            # 提取 P 后的数字部分，补前导0到总长度=原长度+2（补2位）
            num_part = ''.join([c for c in addr if c.isdigit() or c == 'X'])
            padded_num = num_part.zfill(len(num_part) + self.cxba_bits)
            return f"P{padded_num}"
        return addr  # 非 P 开头地址不补位

    def _resolve_dynamic_addr(self, addr: str) -> List[str]:
        """解析动态地址（P001X → P0010-P0019）"""
        if "X" not in addr:
            return [self._pad_address(addr)]
        # 替换 X 为 0-9，生成10个动态地址
        return [self._pad_address(addr.replace("X", str(i))) for i in range(10)]

    def _parse_operation(self, op_str: str) -> int:
        """解析加减组合操作（pom=减1，pov=加1，嵌套/连字符=顺序叠加）"""
        # 去除括号和连字符，提取所有操作指令
        clean_op = op_str.replace("(", "").replace(")", "").replace("-", "")
        op_count = 0
        for op in clean_op:
            if op == "m":  # pom 的核心标识（取首字母简化，也可完整匹配）
                op_count -= 1
            elif op == "v":  # pov 的核心标识
                op_count += 1
        return op_count  # 净操作数（比如 pom-pom(pov(pov(pom] → -1-1+1+1-1 = -1）

    def _get_target_value(self, target: str) -> int:
        """获取目标地址的当前值（内存/磁盘）"""
        if target.startswith("P"):
            # 编辑器内存：默认初始值0
            return self.editor_memory.get(self._pad_address(target), 0)
        elif target.startswith(("C:", "D:")):
            # 磁盘：读取配置文件中的值（默认0）
            disk_path = self.disk_map[target.split(":")[0] + ":"]
            config_file = os.path.join(disk_path, f"{target.replace(':', '_')}.json")
            if os.path.exists(config_file):
                with open(config_file, "r") as f:
                    return json.load(f).get("value", 0)
            return 0
        else:
            raise ValueError(f"不支持的地址类型：{target}")

    def _set_target_value(self, target: str, value: int, is_update: bool = False):
        """设置目标地址的值（内存/磁盘）：s=设置（覆盖），u=更新（累加）"""
        target_padded = self._pad_address(target)
        current_val = self._get_target_value(target)
        final_val = value if not is_update else current_val + value

        if target.startswith("P"):
            # 编辑器内存赋值
            self.editor_memory[target_padded] = final_val
        elif target.startswith(("C:", "D:")):
            # 磁盘赋值（写入配置文件）
            disk_path = self.disk_map[target.split(":")[0] + ":"]
            config_file = os.path.join(disk_path, f"{target.replace(':', '_')}.json")
            with open(config_file, "w") as f:
                json.dump({"value": final_val}, f)

    def parse_sjxeaflist(self, params: List[str]):
        """解析启动/关机参数（sjxeaflist）：启动绑定，关机回收"""
        print("=== 初始化启动参数 ===")
        self._init_disk()
        for param in params:
            if "-" in param:
                # 地址名-值绑定（比如 P2MS0o-g → 地址P2MS0o = g的数值映射，这里简化g=97→ASCII值）
                addr_name, val_char = param.split("-")
                val = ord(val_char)  # 字符转数值（比如 g→103）
                self._set_target_value(addr_name, val)
                print(f"绑定地址 {addr_name} = {val}（字符'{val_char}'的ASCII值）")
            else:
                # 直接初始化地址（默认值0）
                self._set_target_value(param, 0)
                print(f"初始化地址 {param} = 0")

    def parse_loop_header(self, header: str):
        """解析循环头部（kaj>:eaa ... :eau P2M30）"""
        # 拆分循环头部元素（简化解析，保留核心逻辑）
        parts = header.replace("kaj>:eaa ", "").replace(":eas ", "").replace(":eau ", "").split("{g ")
        loop_ops = parts[0].split(" ")
        self.terminate_constant = int(parts[1].replace("]:", ""))  # 提取终止常量 C3113941521

        # 初始化循环计数器（P2M81）和条件判断器（P2M82）
        for i in range(0, len(loop_ops), 2):
            target = loop_ops[i]
            op_str = loop_ops[i+1]
            net_op = self._parse_operation(op_str)
            self._set_target_value(target, net_op)
            print(f"循环初始化：{target} 执行操作 {op_str} → 净操作 {net_op}")
        print(f"循环终止条件：P02M81 的值 == {self.terminate_constant}")

    def parse_loop_body(self, body: List[str]):
        """解析循环体（:cod -| ... |-]）"""
        print("\n=== 开始循环执行 ===")
        loop_count = 0
        while self.loop_running:
            loop_count += 1
            print(f"\n--- 循环第 {loop_count} 次 ---")

            for line in body:
                line = line.strip()
                if not line:
                    continue

                # 解析 u -a 指令（更新+算术模式）
                if line.startswith("u -a"):
                    # 提取目标地址、cxba偏移量（比如 u -a -|s P0113:cxba 2|-]）
                    target = line.split("s ")[1].split(":")[0]
                    offset = int(line.split("cxba ")[1].split("|")[0])
                    # 补位+偏移：P0113→P00113 + 偏移2 → 实际操作地址P00115（这里简化为数值累加偏移）
                    net_op = offset  # 偏移量作为操作数（可根据需求调整）
                    self._set_target_value(target, net_op, is_update=True)
                    print(f"更新算术操作：{target}（补2位+偏移{offset}）→ 当前值 {self._get_target_value(target)}")

                # 解析 s 指令（设置）
                elif line.startswith("s "):
                    parts = line.split(" ", 2)
                    target = parts[1]
                    op_str = parts[2].rstrip("]")  # 去除结尾的 ]
                    net_op = self._parse_operation(op_str)
                    # 处理动态地址（P001X → 批量设置）
                    dynamic_addrs = self._resolve_dynamic_addr(target)
                    for addr in dynamic_addrs:
                        self._set_target_value(addr, net_op)
                        print(f"设置操作：{addr} 执行 {op_str} → 净操作 {net_op} → 当前值 {self._get_target_value(addr)}")

                # 解析 u 指令（更新核心标识）
                elif line.startswith("u CN"):
                    target = line.split("u ")[1]
                    # 核心标识更新：每次循环+1（模拟密钥刷新）
                    current_val = self._get_target_value(target)
                    self._set_target_value(target, current_val + 1)
                    print(f"更新核心标识：{target} → 当前值 {self._get_target_value(target)}")

            # 检查循环终止条件（P02M81 的值 == 终止常量）
            p2m81_val = self._get_target_value("P2M81")
            if p2m81_val >= self.terminate_constant:  # 简化为>=，避免死循环
                self.loop_running = False
                print(f"\n循环终止：P02M81 = {p2m81_val} 达到终止常量 {self.terminate_constant}")

    def shutdown(self):
        """关机：回收资源"""
        print("\n=== 关机：回收资源 ===")
        # 清空编辑器内存
        self.editor_memory.clear()
        print("已清空编辑器内存")
        # 可选：删除磁盘配置文件（模拟资源回收）
        for path in self.disk_map.values():
            for file in os.listdir(path):
                os.remove(os.path.join(path, file))
            os.rmdir(path)
        print("已删除磁盘配置文件，释放资源")

    def run_program(self, program: List[str]):
        """运行你的自定义汇编程序"""
        print("=== PomPov 编辑器启动 ===")
        loop_header = ""
        loop_body = []
        in_loop = False
        in_loop_body = False

        for line in program:
            line = line.strip()
            if not line:
                continue

            # 1. 解析启动参数
            if line.startswith("sjxeaflist"):
                params = line.split(" ")[1:]
                self.parse_sjxeaflist(params)

            # 2. 解析循环头部（kaj=循环）
            elif line.startswith("kaj"):
                loop_header = line
                self.parse_loop_header(loop_header)
                in_loop = True

            # 3. 解析循环体开始
            elif line == ":cod -|":
                in_loop_body = True

            # 4. 解析循环体结束
            elif line == "|-]":
                if in_loop_body:
                    in_loop_body = False
                    self.loop_running = True
                    self.parse_loop_body(loop_body)
                    loop_body = []
                in_loop = False

            # 5. 收集循环体内容
            elif in_loop_body:
                loop_body.append(line)

            # 6. 解析普通设置指令（s=设置）
            elif line.startswith("s "):
                parts = line.split(" ", 2)
                target = parts[1]
                op_str = parts[2].rstrip("]")
                net_op = self._parse_operation(op_str)
                self._set_target_value(target, net_op)
                print(f"普通设置：{target} 执行 {op_str} → 净操作 {net_op} → 当前值 {self._get_target_value(target)}")

        # 程序执行完毕，关机回收
        self.shutdown()

# ------------------------------
# 你的自定义汇编程序（直接复制过来）
# ------------------------------
your_program = [
    "s P0300 pov",
    "s p0314 pov",  # 不区分大小写，编辑器自动处理
    "s P1209 pom-pom",
    "kaj>:eaa P2M81 pov-pom:eas P2M82 pom-pom(pov(pom({g C3113941521]:eau P2M30",
    ":cod -|",
    "    u -a -|s P0113:cxba 2|-]",
    "    s P001X pom-pom(pov(pov(pom]",
    "    u CN3011SL1198731F",
    "|-]",
    "sjxeaflist P2MS0o-g P2M1H9"
]

# ------------------------------
# 运行编辑器
# ------------------------------
if __name__ == "__main__":
    editor = PomPovEditor()
    editor.run_program(your_program)