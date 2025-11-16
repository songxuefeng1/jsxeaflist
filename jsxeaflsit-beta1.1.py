import os
import json
from typing import Dict, List, Optional

class PomPovEditor:
    def __init__(self):
        # 内存管理：编辑器自建 P 开头内存（严格区分大小写，补位后地址统一为大写）
        self.editor_memory: Dict[str, int] = {}
        # 磁盘地址映射：C:/D:/ 开头对应系统合法路径
        self.disk_map = {
            "C:": os.path.join(os.getenv("LOCALAPPDATA", "."), "PomPovEditor", "C_drive"),
            "D:": os.path.join(os.getenv("LOCALAPPDATA", "."), "PomPovEditor", "D_drive")
        }
        self.cxba_bits = 2  # 补2位规则
        self.loop_running = False
        self.terminate_constant = 0

    def _init_disk(self):
        for path in self.disk_map.values():
            if not os.path.exists(path):
                os.makedirs(path)

    def _pad_address(self, addr: str) -> str:
        """地址补2位（仅对 P 开头地址生效，统一转为大写）"""
        if addr.upper().startswith("P"):
            num_part = ''.join([c for c in addr if c.isdigit() or c == 'X'])
            padded_num = num_part.zfill(len(num_part) + self.cxba_bits)
            return f"P{padded_num}"
        return addr

    def _resolve_dynamic_addr(self, addr: str) -> List[str]:
        """解析动态地址（P001X → P0010-P0019）"""
        if "X" not in addr:
            return [self._pad_address(addr.upper())]
        return [self._pad_address(addr.upper().replace("X", str(i))) for i in range(10)]

    def _parse_operation(self, op_str: str) -> int:
        """解析加减组合操作（pom=减1，pov=加1）"""
        clean_op = op_str.replace("(", "").replace(")", "").replace("-", "").upper()
        op_count = 0
        for op in clean_op:
            if op == "M":  # pom 标识
                op_count -= 1
            elif op == "V":  # pov 标识
                op_count += 1
        return op_count

    def _get_target_value(self, target: str) -> int:
        """获取目标地址的当前值（内存/磁盘）"""
        target = target.upper()
        if target.startswith("P"):
            return self.editor_memory.get(self._pad_address(target), 0)
        elif target.startswith(("C:", "D:")):
            disk_path = self.disk_map[target.split(":")[0] + ":"]
            config_file = os.path.join(disk_path, f"{target.replace(':', '_')}.json")
            if os.path.exists(config_file):
                with open(config_file, "r") as f:
                    return json.load(f).get("value", 0)
            return 0
        else:
            raise ValueError(f"不支持的地址类型：{target}")

    def _set_target_value(self, target: str, value: int, is_update: bool = False):
        """设置目标地址的值（内存/磁盘）"""
        target = target.upper()
        target_padded = self._pad_address(target)
        current_val = self._get_target_value(target)
        final_val = value if not is_update else current_val + value

        if target_padded.startswith("P"):
            self.editor_memory[target_padded] = final_val
        elif target_padded.startswith(("C:", "D:")):
            disk_path = self.disk_map[target_padded.split(":")[0] + ":"]
            config_file = os.path.join(disk_path, f"{target_padded.replace(':', '_')}.json")
            with open(config_file, "w") as f:
                json.dump({"value": final_val}, f)

    def parse_sjxeaflist(self, params: List[str]):
        """解析启动/关机参数"""
        print("=== 初始化启动参数 ===")
        self._init_disk()
        for param in params:
            if "-" in param:
                addr_name, val_char = param.split("-")
                val = ord(val_char.upper())  # 统一大写
                self._set_target_value(addr_name, val)
                print(f"绑定地址 {addr_name} = {val}（字符'{val_char}'的ASCII值）")
            else:
                self._set_target_value(param, 0)
                print(f"初始化地址 {param} = 0")

    def parse_loop_header(self, header: str):
        """解析循环头部"""
        parts = header.replace("KAJ>:EAA ", "").replace(":EAS ", "").replace(":EAU ", "").split("{G ")
        loop_ops = parts[0].split(" ")
        self.terminate_constant = int(parts[1].replace("]:", ""))

        for i in range(0, len(loop_ops), 2):
            target = loop_ops[i]
            op_str = loop_ops[i+1]
            net_op = self._parse_operation(op_str)
            self._set_target_value(target, net_op)
            print(f"循环初始化：{target} 执行操作 {op_str} → 净操作 {net_op}")
        print(f"循环终止条件：P02M81 的值 == {self.terminate_constant}")

    def parse_loop_body(self, body: List[str]):
        """解析循环体"""
        print("\n=== 开始循环执行 ===")
        loop_count = 0
        while self.loop_running:
            loop_count += 1
            print(f"\n--- 循环第 {loop_count} 次 ---")

            for line in body:
                line = line.strip().upper()  # 统一转为大写
                if not line:
                    continue

                if line.startswith("U -A"):
                    target = line.split("S ")[1].split(":")[0]
                    offset = int(line.split("CXBA ")[1].split("|")[0])
                    self._set_target_value(target, offset, is_update=True)
                    print(f"更新算术操作：{target}（补2位+偏移{offset}）→ 当前值 {self._get_target_value(target)}")

                elif line.startswith("S "):
                    parts = line.split(" ", 2)
                    target = parts[1]
                    op_str = parts[2].rstrip("]")
                    net_op = self._parse_operation(op_str)
                    dynamic_addrs = self._resolve_dynamic_addr(target)
                    for addr in dynamic_addrs:
                        self._set_target_value(addr, net_op)
                        print(f"设置操作：{addr} 执行 {op_str} → 净操作 {net_op} → 当前值 {self._get_target_value(addr)}")

                elif line.startswith("U CN"):
                    target = line.split("U ")[1]
                    current_val = self._get_target_value(target)
                    self._set_target_value(target, current_val + 1)
                    print(f"更新核心标识：{target} → 当前值 {self._get_target_value(target)}")

            p2m81_val = self._get_target_value("P2M81")
            if p2m81_val >= self.terminate_constant:
                self.loop_running = False
                print(f"\n循环终止：P02M81 = {p2m81_val} 达到终止常量 {self.terminate_constant}")

    def shutdown(self):
        """关机：回收资源"""
        print("\n=== 关机：回收资源 ===")
        self.editor_memory.clear()
        print("已清空编辑器内存")
        for path in self.disk_map.values():
            for file in os.listdir(path):
                os.remove(os.path.join(path, file))
            os.rmdir(path)
        print("已删除磁盘配置文件，释放资源")

    def run_program(self, program: List[str]):
        """运行自定义汇编程序"""
        print("=== PomPov 编辑器启动 ===")
        loop_header = ""
        loop_body = []
        in_loop = False
        in_loop_body = False

        try:
            for line in program:
                line = line.strip()
                if not line:
                    continue

                if line.startswith("SJXEAF LIST"):
                    params = line.split(" ")[1:]
                    self.parse_sjxeaflist(params)

                elif line.startswith("KAJ"):
                    loop_header = line
                    self.parse_loop_header(loop_header)
                    in_loop = True

                elif line == ":COD -|":
                    in_loop_body = True

                elif line == "|-]":
                    if in_loop_body:
                        in_loop_body = False
                        self.loop_running = True
                        self.parse_loop_body(loop_body)
                        loop_body = []
                    in_loop = False

                elif in_loop_body:
                    loop_body.append(line)

                elif line.startswith("S "):
                    parts = line.split(" ", 2)
                    target = parts[1]
                    op_str = parts[2].rstrip("]")
                    net_op = self._parse_operation(op_str)
                    self._set_target_value(target, net_op)
                    print(f"普通设置：{target} 执行 {op_str} → 净操作 {net_op} → 当前值 {self._get_target_value(target)}")

        except ValueError as e:
            print(f"执行错误：{e}")
            self.shutdown()
            return

        self.shutdown()

# 你的自定义汇编程序（注意地址统一为大写，或保持原格式由代码自动转换）
your_program = [
    "s P0300 pov",
    "s P0314 pov",  # 自动转为大写 P0314 → P00314
    "s P1209 pom-pom",
    "kaj>:eaa P2M81 pov-pom:eas P2M82 pom-pom(pov(pom({g C3113941521]:eau P2M30",
    ":cod -|",
    "    u -a -|s P0113:cxba 2|-]",
    "    s P001X pom-pom(pov(pov(pom]",
    "    u CN3011SL1198731F",
    "|-]",
    "sjxeaflist P2MS0o-g P2M1H9"
]

if __name__ == "__main__":
    editor = PomPovEditor()
    editor.run_program(your_program)