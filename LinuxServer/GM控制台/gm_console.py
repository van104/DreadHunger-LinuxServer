#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dread Hunger Linux GM 控制台 (Vue 3 + Element Plus 暗黑科技版)
监听 0.0.0.0:9900，提供 Web GM 操作面板。
通过写入 gm_commands.json 与 Frida 插件通信。
"""

from __future__ import annotations
import argparse, hashlib, hmac, html, json, math, os, re, secrets, sys, time, uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit
import threading

VERSION = "1.8.0"
DEFAULT_PASSWORD = "admin"
COMMAND_FILE = "gm_commands.json"
PLAYER_LIST_FILE = "gm_player_list.json"
GM_RUNTIME_DIR = ".gm_runtime"
COMMAND_RESULT_DIR = "gm_results"
COMMAND_RESULT_TIMEOUT = 3.0
COMMAND_RESULT_MAX_AGE = 600
MAX_COORDINATE = 10_000_000.0
BLACKLIST_FILE = "gm_blacklist.json"
BLACKLIST_CHECK_TOKEN_FILE = "gm_blacklist_check_token.txt"
TELEPORT_PRESETS_FILE = "gm_teleport_presets.json"
WINNING_CARD_REWARD_FILE = "gm_winning_card_reward.json"
DEFAULT_WINNING_CARD_REWARD = {
    "enabled": False,
    "mode": "fixed",
    "delay_seconds": 30,
    "backpack_slots": 0,
    "items": [{"item": "coal", "quantity": 5}],
    "announcement": "[牌局奖励] {player} 获得开局奖励：{rewards}",
}
BLACKLIST_REASON_PRESETS = {
    "quit_after_death": "死一次退",
    "griefing": "恶意摆烂",
    "cheating": "使用外挂",
    "bug_abuse": "恶意卡 Bug",
    "harassment": "辱骂或骚扰",
    "other": "其他",
}
LOGIN_PATTERN = re.compile(
    r"LogNet:\s*Login request:\s*\?Name=(?P<name>.+?)\s+userId:\s*(?P<uid>[^\s]+)"
    r"(?:\s+platform:\s*(?P<platform>[^\s]+))?"
)
STEAM_ID_PATTERN = re.compile(r"^\d{17}$")
EOS_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
FULL_USER_ID_PATTERN = re.compile(r"^(?P<steam>\d{17})_\+_\|(?P<eos>[0-9a-fA-F]{32})$")
ROLE_NAMES = {
    "Captain": "船长",
    "Chaplain": "牧师",
    "Cook": "厨子",
    "Doctor": "医生",
    "Engineer": "工程",
    "Hunter": "猎人",
    "Marine": "枪手",
    "Navigator": "导航",
}


def item(item_id: str, name: str, category: str, class_path: str, *, special=False, requires_mod=False):
    return {
        "id": item_id,
        "name": name,
        "category": category,
        "class_path": class_path,
        "special": bool(special),
        "requires_mod": bool(requires_mod),
    }


ITEM_CATALOG = [
    item("fists", "拳头", "特殊", "/Game/Blueprints/Inventory/Fists/BP_Fists_Inventory.BP_Fists_Inventory_C", special=True),
    item("flintlock", "燧发手枪", "远程武器", "/Game/Blueprints/Inventory/Flintlock/BP_Flintlock_Inventory.BP_Flintlock_Inventory_C"),
    item("musket", "步枪", "远程武器", "/Game/Blueprints/Inventory/Musket/BP_Musket_Inventory.BP_Musket_Inventory_C"),
    item("bow", "弓", "远程武器", "/Game/Blueprints/Inventory/Bow/BP_Bow_Inventory.BP_Bow_Inventory_C"),
    item("gun_parts", "枪械零件", "远程武器", "/Game/Blueprints/Inventory/Flint/BP_GunParts_Inventory.BP_GunParts_Inventory_C"),
    item("flintlock_ammo", "子弹", "弹药", "/Game/Blueprints/Inventory/Flintlock/BP_Flintlock_Ammo_Inventory.BP_Flintlock_Ammo_Inventory_C"),
    item("arrows", "箭", "弹药", "/Game/Blueprints/Inventory/Bow/BP_Arrows_Inventory.BP_Arrows_Inventory_C"),
    item("sword", "军刀", "近战武器", "/Game/Blueprints/Inventory/Sword/BP_Sword_Inventory.BP_Sword_Inventory_C"),
    item("wood_axe", "斧头", "近战武器", "/Game/Blueprints/Inventory/WoodAxe/BP_WoodAxe_Inventory.BP_WoodAxe_Inventory_C"),
    item("ice_axe", "冰镐", "近战武器", "/Game/Blueprints/Inventory/IceAxe/BP_IceAxe_Inventory.BP_IceAxe_Inventory_C"),
    item("cleaver", "菜刀", "近战武器", "/Game/Blueprints/Inventory/Cleaver/BP_Cleaver_Inventory.BP_Cleaver_Inventory_C"),
    item("shovel", "铲子", "近战武器", "/Game/Blueprints/Inventory/Shovel/BP_Shovel_Inventory.BP_Shovel_Inventory_C"),
    item("stick", "木板", "材料", "/Game/Blueprints/Inventory/Stick/BP_Stick_Inventory.BP_Stick_Inventory_C"),
    item("rock", "石头", "材料", "/Game/Blueprints/Inventory/Rock/BP_Rock_Inventory.BP_Rock_Inventory_C"),
    item("iron_ingot", "废铁", "材料", "/Game/Blueprints/Inventory/Metals/BP_IronIngot_Inventory.BP_IronIngot_Inventory_C"),
    item("nails", "钉子", "材料", "/Game/Blueprints/Inventory/Metals/BP_Nails_Inventory.BP_Nails_Inventory_C"),
    item("lead_ingot", "铅锭", "材料", "/Game/Blueprints/Inventory/Metals/BP_LeadIngot_Inventory.BP_LeadIngot_Inventory_C"),
    item("coal", "煤炭", "材料", "/Game/Blueprints/Inventory/Coal/BP_Coal_Inventory.BP_Coal_Inventory_C"),
    item("gunpowder", "火药", "材料", "/Game/Blueprints/Inventory/Flintlock/BP_Gunpowder_Inventory.BP_Gunpowder_Inventory_C"),
    item("sinew", "肌腱", "材料", "/Game/Blueprints/Inventory/AnimalParts/BP_Sinew_Inventory.BP_Sinew_Inventory_C"),
    item("wolf_pelt", "动物皮毛", "材料", "/Game/Blueprints/Inventory/AnimalParts/BP_WolfPelt_Inventory.BP_WolfPelt_Inventory_C"),
    item("herbs", "草药", "材料", "/Game/Blueprints/Inventory/Tea/BP_Herbs_Inventory.BP_Herbs_Inventory_C"),
    item("syringe", "针筒", "恢复品", "/Game/Blueprints/Inventory/Syringe/BP_Syringe_Inventory.BP_Syringe_Inventory_C"),
    item("antidote", "解毒剂", "恢复品", "/Game/Blueprints/Inventory/Poison/BP_Antidote_Inventory.BP_Antidote_Inventory_C"),
    item("laudanum", "鸦片酊", "恢复品", "/Game/Blueprints/Inventory/Syringe/BP_Inventory_Laudanum.BP_Inventory_Laudanum_C"),
    item("animal_meat", "兽肉", "食物", "/Game/Blueprints/Inventory/Meat/BP_AnimalMeat_Inventory.BP_AnimalMeat_Inventory_C"),
    item("cooked_meat", "熟兽肉", "食物", "/Game/Blueprints/Inventory/Meat/BP_CookedMeat_Inventory.BP_CookedMeat_Inventory_C"),
    item("human_meat", "人肉", "食物", "/Game/Blueprints/Inventory/Meat/BP_HumanMeat_Inventory.BP_HumanMeat_Inventory_C"),
    item("bone_club", "骨棒", "食物", "/Game/Blueprints/Inventory/Meat/BP_BoneClub_Inventory.BP_BoneClub_Inventory_C"),
    item("blubber", "脂肪", "食物", "/Game/Blueprints/Inventory/AnimalParts/BP_Blubber_Inventory.BP_Blubber_Inventory_C"),
    item("stew", "炖肉", "食物", "/Game/Blueprints/Inventory/Meat/BP_Stew_Inventory.BP_Stew_Inventory_C"),
    item("tea", "茶", "食物", "/Game/Blueprints/Inventory/Tea/BP_Tea_Inventory.BP_Tea_Inventory_C"),
    item("whetstone", "磨刀石", "工具", "/Game/Blueprints/Inventory/Metals/BP_Whetstone_Inventory.BP_Whetstone_Inventory_C"),
    item("bear_trap", "捕兽夹", "工具", "/Game/Blueprints/Inventory/BearTrap/BP_BearTrap_Inventory.BP_BearTrap_Inventory_C"),
    item("spyglass", "望远镜", "工具", "/Game/Blueprints/Inventory/Spyglass/BP_Spyglass_Inventory.BP_Spyglass_Inventory_C"),
    item("lantern", "灯笼", "工具", "/Game/Blueprints/Inventory/Lantern/BP_Lantern_Inventory.BP_Lantern_Inventory_C"),
    item("coal_barrel", "煤炭桶", "爆炸物", "/Game/Blueprints/Inventory/Powderkeg/BP_CoalBarrel_Inventory.BP_CoalBarrel_Inventory_C"),
    item("powderkeg", "炸药桶", "爆炸物", "/Game/Blueprints/Inventory/Powderkeg/BP_Powderkeg_Inventory.BP_Powderkeg_Inventory_C"),
    item("poison", "毒药", "爆炸物", "/Game/Blueprints/Inventory/Poison/BP_Poison_Inventory.BP_Poison_Inventory_C"),
    item("nitro", "硝化甘油", "爆炸物", "/Game/Blueprints/Environment/Nitro/BP_Nitro_Inventory.BP_Nitro_Inventory_C"),
    item("skeleton_key", "万能钥匙", "钥匙与任务", "/Game/Blueprints/Inventory/LockPick/BP_SkeletonKey_Inventory.BP_SkeletonKey_Inventory_C"),
    item("captains_key", "船长钥匙", "钥匙与任务", "/Game/Blueprints/Inventory/LockPick/BP_CaptainsKey_Inventory.BP_CaptainsKey_Inventory_C"),
    item("armory_code", "军械库密码", "钥匙与任务", "/Game/Blueprints/Inventory/Armory/BP_Code_Inventory.BP_Code_Inventory_C", special=True),
    item("bone_dagger", "骸骨匕首", "钥匙与任务", "/Game/Blueprints/Inventory/Totem/BP_BoneDagger_Inventory.BP_BoneDagger_Inventory_C", special=True),
    item("quest", "任务卷轴", "钥匙与任务", "/Game/Blueprints/Inventory/Quest/BP_Quest_Inventory.BP_Quest_Inventory_C", special=True),
    item("backpack", "背包", "特殊", "/Game/Blueprints/Inventory/Backpack/BP_Backpack_Inventory.BP_Backpack_Inventory_C", special=True),
    item("human_body", "人类尸体", "特殊", "/Game/Blueprints/Player/BP_HumanBody_Inventory.BP_HumanBody_Inventory_C", special=True),
    item("human_arm", "人类手臂", "特殊", "/Game/Blueprints/Player/Gore/BP_Human_Arm_Inventory.BP_Human_Arm_Inventory_C", special=True),
    item("human_head", "人类头颅", "特殊", "/Game/Blueprints/Player/Gore/BP_Human_Head_Inventory.BP_Human_Head_Inventory_C", special=True),
    item("human_leg", "人类腿", "特殊", "/Game/Blueprints/Player/Gore/BP_Human_Leg_Inventory.BP_Human_Leg_Inventory_C", special=True),
    item("bear_head", "熊头", "特殊", "/Game/Blueprints/AI/Predators/Gore/BP_Bear_Head_Inventory.BP_Bear_Head_Inventory_C", special=True),
    item("wolf_head", "狼头", "特殊", "/Game/Blueprints/AI/Predators/Gore/BP_Wolf_Head_Inventory.BP_Wolf_Head_Inventory_C", special=True),
    item("wolf_leg", "狼腿", "特殊", "/Game/Blueprints/AI/Predators/Gore/BP_Wolf_Leg_Inventory.BP_Wolf_Leg_Inventory_C", special=True),
    item("rabbit_head", "兔头", "特殊", "/Game/Blueprints/AI/Prey/Gore/BP_Rabbit_Head_Inventory.BP_Rabbit_Head_Inventory_C", special=True),
    item("bone_charm", "骨符", "特殊", "/Game/Blueprints/Inventory/Totem/BP_BoneCharm_Inventory.BP_BoneCharm_Inventory_C", special=True, requires_mod=True),
    item("pure_crystal", "纯净水晶", "特殊", "/Game/Mods/Maps/Archipelago/Blueprints/Mission/Explorer/PureCrystal/BP_PureCrystal_Inventory.BP_PureCrystal_Inventory_C", special=True, requires_mod=True),
]
ITEM_BY_ID = {entry["id"]: entry for entry in ITEM_CATALOG}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(str(tmp), 0o666)
    except OSError:
        pass
    os.replace(str(tmp), str(path))


def atomic_write_text(path: Path, value: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(value, encoding="utf-8")
    try:
        os.chmod(str(tmp), mode)
    except OSError:
        pass
    os.replace(str(tmp), str(path))

def read_json(path: Path, fallback: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return fallback


def normalize_player_name(value: Any) -> str:
    return " ".join(html.unescape(str(value or "")).replace("\u200b", "").split()).casefold()


def split_player_user_id(value: Any) -> Dict[str, str]:
    user_id = str(value or "").strip()
    if user_id.startswith("EOSPlus:"):
        user_id = user_id[len("EOSPlus:") :]
    steam_id = ""
    eos_id = ""
    full_match = FULL_USER_ID_PATTERN.fullmatch(user_id)
    if full_match:
        steam_id = full_match.group("steam")
        eos_id = full_match.group("eos").lower()
        user_id = "%s_+_|%s" % (steam_id, eos_id)
    elif STEAM_ID_PATTERN.fullmatch(user_id):
        steam_id = user_id
    elif EOS_ID_PATTERN.fullmatch(user_id):
        eos_id = user_id.lower()
        user_id = eos_id
    return {"user_id": user_id, "steam_id": steam_id, "eos_id": eos_id}


def manual_blacklist_identity(params: Dict[str, Any]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for key in ("user_id", "steam_id", "eos_id"):
        value = params.get(key, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError("Steam/EOS ID 必须以文本填写，不能使用数字格式")
        values[key] = value.strip()

    raw_user_id = values["user_id"]
    if raw_user_id.startswith("EOSPlus:"):
        raw_user_id = raw_user_id[len("EOSPlus:") :]
    parsed = split_player_user_id(raw_user_id)
    if raw_user_id and not (
        STEAM_ID_PATTERN.fullmatch(raw_user_id)
        or EOS_ID_PATTERN.fullmatch(raw_user_id)
        or FULL_USER_ID_PATTERN.fullmatch(raw_user_id)
    ):
        raise ValueError("完整用户 ID 格式错误，应为 SteamID_+_|EOSID，也可只填其中一个 ID")

    steam_id = values["steam_id"]
    eos_id = values["eos_id"].lower()
    if steam_id and not STEAM_ID_PATTERN.fullmatch(steam_id):
        raise ValueError("Steam ID 必须是 17 位数字")
    if eos_id and not EOS_ID_PATTERN.fullmatch(eos_id):
        raise ValueError("EOS ID 必须是 32 位十六进制字符")
    if steam_id and parsed["steam_id"] and steam_id != parsed["steam_id"]:
        raise ValueError("单独填写的 Steam ID 与完整用户 ID 不一致")
    if eos_id and parsed["eos_id"] and eos_id != parsed["eos_id"]:
        raise ValueError("单独填写的 EOS ID 与完整用户 ID 不一致")

    steam_id = steam_id or parsed["steam_id"]
    eos_id = eos_id or parsed["eos_id"]
    if not steam_id and not eos_id:
        raise ValueError("请至少填写 Steam ID、EOS ID 或完整用户 ID 中的一项")
    user_id = "%s_+_|%s" % (steam_id, eos_id) if steam_id and eos_id else (steam_id or eos_id)
    platform = "EOSPlus" if steam_id and eos_id else ("Steam" if steam_id else "EOS")
    return {"user_id": user_id, "steam_id": steam_id, "eos_id": eos_id, "platform": platform}


class GMConsole:
    def __init__(self, root: Path, password: str):
        self.root = root
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()
        self.session_tokens = set()
        self.lock = threading.Lock()
        self.blacklist_lock = threading.RLock()
        self.teleport_presets_lock = threading.RLock()
        self.winning_card_reward_lock = threading.RLock()
        self.runtime_dir = root / GM_RUNTIME_DIR
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.command_path = self.runtime_dir / COMMAND_FILE
        self.player_list_path = self.runtime_dir / PLAYER_LIST_FILE
        self.result_dir = self.runtime_dir / COMMAND_RESULT_DIR
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.blacklist_path = root / BLACKLIST_FILE
        self.blacklist_check_token_path = root / BLACKLIST_CHECK_TOKEN_FILE
        self.teleport_presets_path = root / TELEPORT_PRESETS_FILE
        self.winning_card_reward_path = root / WINNING_CARD_REWARD_FILE
        self.game_log_path = root / "DreadHunger" / "Saved" / "Logs" / "DreadHunger.log"
        self.blacklist_check_token = self._load_or_create_blacklist_check_token()

    def _load_or_create_blacklist_check_token(self) -> str:
        try:
            token = self.blacklist_check_token_path.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
        if len(token) < 24:
            token = secrets.token_urlsafe(32)
            atomic_write_text(self.blacklist_check_token_path, token + "\n")
        return token

    def valid_blacklist_check_token(self, token: str) -> bool:
        return bool(token) and hmac.compare_digest(token, self.blacklist_check_token)

    def check_password(self, pwd: str) -> bool:
        return hmac.compare_digest(hashlib.sha256(pwd.encode()).hexdigest(), self.password_hash)

    def create_session(self) -> str:
        token = secrets.token_urlsafe(32)
        self.session_tokens.add(token)
        return token

    def valid_session(self, token: str) -> bool:
        return bool(token) and token in self.session_tokens

    def invalidate(self, token: str) -> None:
        self.session_tokens.discard(token)

    def get_items(self) -> dict:
        fields = ("id", "name", "category", "special", "requires_mod")
        return {
            "ok": True,
            "count": len(ITEM_CATALOG),
            "max_quantity": 20,
            "items": [{key: entry[key] for key in fields} for entry in ITEM_CATALOG],
        }

    def _normalize_winning_card_reward(self, params: dict) -> dict:
        enabled = params.get("enabled") is True
        mode = str(params.get("mode") or "fixed").strip()
        if mode not in {"fixed", "random"}:
            raise ValueError("奖励模式只能选择固定奖励或随机奖励")

        delay_seconds = params.get("delay_seconds")
        if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, int) or not 0 <= delay_seconds <= 600:
            raise ValueError("发放时间必须是开局后 0 到 600 秒的整数")

        backpack_slots = params.get("backpack_slots")
        if isinstance(backpack_slots, bool) or not isinstance(backpack_slots, int) or not 0 <= backpack_slots <= 30:
            raise ValueError("背包总格数必须是 0 到 30 的整数")

        raw_items = params.get("items")
        if not isinstance(raw_items, list) or len(raw_items) > 8:
            raise ValueError("奖励物品必须是列表，最多添加 8 种")
        items = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise ValueError("奖励物品格式无效")
            item_id = str(raw.get("item") or "").strip()
            entry = ITEM_BY_ID.get(item_id)
            if entry is None:
                raise ValueError("奖励物品无效: " + item_id)
            quantity = raw.get("quantity")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 20:
                raise ValueError("每种奖励物品数量必须是 1 到 20 的整数")
            items.append({
                "item": item_id,
                "item_name": entry["name"],
                "item_class": entry["class_path"],
                "quantity": quantity,
            })

        if enabled and backpack_slots == 0 and not items:
            raise ValueError("启用奖励时，至少设置背包格数或一种物品")

        announcement = str(params.get("announcement") or "").strip()
        if len(announcement) > 500:
            raise ValueError("公告内容不能超过 500 个字符")
        return {
            "enabled": enabled,
            "mode": mode,
            "delay_seconds": delay_seconds,
            "backpack_slots": backpack_slots,
            "items": items,
            "announcement": announcement,
        }

    def get_winning_card_reward(self) -> dict:
        with self.winning_card_reward_lock:
            data = read_json(self.winning_card_reward_path, DEFAULT_WINNING_CARD_REWARD)
            try:
                config = self._normalize_winning_card_reward(data if isinstance(data, dict) else {})
            except ValueError:
                config = self._normalize_winning_card_reward(dict(DEFAULT_WINNING_CARD_REWARD))
            return {"ok": True, "config": config}

    def save_winning_card_reward(self, params: dict) -> dict:
        config = self._normalize_winning_card_reward(params)
        with self.winning_card_reward_lock:
            atomic_write_json(self.winning_card_reward_path, config)
        return {"ok": True, "config": config, "saved_at": now_text()}

    def _validate_online_role(self, value: Any) -> str:
        role = str(value or "").strip()
        if role not in ROLE_NAMES:
            raise ValueError("职业无效")
        players = self.get_players()
        if players.get("stale"):
            raise ValueError("玩家列表已过期，请确认 Frida 正常运行")
        if not any(player.get("role_id") == role for player in players.get("players", [])):
            raise ValueError("所选职业当前不在线")
        return role

    def _validate_online_player(self, value: Any) -> str:
        player_name = str(value or "").strip()
        if not player_name:
            raise ValueError("未指定玩家")
        players = self.get_players()
        if players.get("stale"):
            raise ValueError("玩家列表已过期，请确认 Frida 正常运行")
        normalized_name = normalize_player_name(player_name)
        for player in players.get("players", []):
            if normalize_player_name(player.get("name")) == normalized_name:
                return str(player.get("name") or player_name)
        raise ValueError("玩家当前不在线")

    def _normalize_coordinates(self, params: dict) -> dict:
        coordinates = {}
        for key in ("x", "y", "z"):
            value = params.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("坐标必须是数字")
            value = float(value)
            if not math.isfinite(value) or abs(value) > MAX_COORDINATE:
                raise ValueError("坐标超出安全范围")
            coordinates[key] = value
        return coordinates

    def get_teleport_presets(self) -> dict:
        with self.teleport_presets_lock:
            data = read_json(self.teleport_presets_path, {"presets": []})
            presets = data.get("presets", []) if isinstance(data, dict) else []
            if not isinstance(presets, list):
                presets = []
            presets = [entry for entry in presets if isinstance(entry, dict)]
            return {"ok": True, "count": len(presets), "presets": presets}

    def save_teleport_preset(self, params: dict) -> dict:
        name = str(params.get("name") or "").strip()
        if not name or len(name) > 40:
            raise ValueError("预设名称长度必须为 1 到 40 个字符")
        coordinates = self._normalize_coordinates(params)
        preset = {"name": name, **coordinates, "updated_at": now_text()}
        with self.teleport_presets_lock:
            data = self.get_teleport_presets()
            presets = [entry for entry in data["presets"] if str(entry.get("name") or "") != name]
            presets.append(preset)
            atomic_write_json(self.teleport_presets_path, {"presets": presets})
        return {"ok": True, "preset": preset}

    def remove_teleport_preset(self, params: dict) -> dict:
        name = str(params.get("name") or "").strip()
        if not name:
            raise ValueError("未指定预设名称")
        with self.teleport_presets_lock:
            data = self.get_teleport_presets()
            presets = [entry for entry in data["presets"] if str(entry.get("name") or "") != name]
            if len(presets) == len(data["presets"]):
                raise ValueError("预设点位不存在")
            atomic_write_json(self.teleport_presets_path, {"presets": presets})
        return {"ok": True, "removed": name}

    def normalize_action_params(self, action: str, params: dict) -> dict:
        normalized = dict(params or {})
        if action == "give_item" and str(normalized.get("role") or "").strip() == "all":
            normalized["role"] = "all"
        elif action in {"give_item", "execute_player"}:
            normalized["role"] = self._validate_online_role(normalized.get("role"))
        elif action == "teleport_player":
            if normalized.get("player"):
                normalized["player"] = self._validate_online_player(normalized.get("player"))
            else:
                normalized["role"] = self._validate_online_role(normalized.get("role"))
        elif action in {"revive_player", "teleport_to_ship"} and normalized.get("role"):
            normalized["role"] = self._validate_online_role(normalized.get("role"))

        if action == "give_item":
            item_id = str(normalized.get("item") or "").strip()
            entry = ITEM_BY_ID.get(item_id)
            if entry is None:
                raise ValueError("物品无效")
            quantity = normalized.get("quantity")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 20:
                raise ValueError("物品数量必须是 1 到 20 的整数")
            normalized["item"] = item_id
            normalized["item_name"] = entry["name"]
            normalized["item_class"] = entry["class_path"]
            normalized["quantity"] = quantity

        if action == "teleport_player":
            normalized.update(self._normalize_coordinates(normalized))
        return normalized

    def _cleanup_results(self) -> None:
        cutoff = time.time() - COMMAND_RESULT_MAX_AGE
        for path in self.result_dir.glob("*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass

    def wait_for_result(self, command_id: str, timeout: float = COMMAND_RESULT_TIMEOUT) -> Optional[dict]:
        result_path = self.result_dir / (command_id + ".json")
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            result = read_json(result_path, None)
            if isinstance(result, dict) and result.get("id") == command_id:
                try:
                    result_path.unlink()
                except OSError:
                    pass
                return result
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)

    def send_command(self, action: str, params: dict) -> dict:
        """下发单条命令并短暂等待 Frida 返回真实执行结果。"""
        params = self.normalize_action_params(action, params)
        self._cleanup_results()
        cmd = {"id": str(uuid.uuid4()), "action": action, "params": params, "time": now_text()}
        with self.lock:
            atomic_write_json(self.command_path, {"commands": [cmd]})
            envelope = self.wait_for_result(cmd["id"])
        action_desc = {
            "open_armory": "成功开启军械库",
            "end_game": "成功下发结束对局指令",
            "skip_poker": "成功跳过打牌并开始游戏",
            "send_message": "成功发送消息",
            "kick_player": "成功踢出玩家",
            "revive_player": "成功复活玩家",
            "teleport_to_ship": "成功传送玩家回船",
            "give_item": "成功发送物品",
            "teleport_player": "成功传送玩家",
            "execute_player": "成功处决并安排踢出玩家",
        }.get(action, f"成功执行 {action}")
        if envelope is not None:
            result = envelope.get("result") if isinstance(envelope.get("result"), dict) else {}
            if result.get("success") is True:
                return {
                    "ok": True,
                    "success": True,
                    "queued": False,
                    "message": str(result.get("message") or action_desc),
                    "command_id": cmd["id"],
                    "action": action,
                    "params": params,
                    "result": result,
                    "time": cmd["time"],
                }
            return {
                "ok": False,
                "success": False,
                "queued": False,
                "error": str(result.get("error") or envelope.get("error") or "Frida 执行失败"),
                "command_id": cmd["id"],
                "action": action,
                "result": result,
                "time": cmd["time"],
            }
        return {
            "ok": True,
            "success": True,
            "queued": True,
            "message": "指令已下发，等待 Frida 执行结果",
            "command_id": cmd["id"],
            "action": action,
            "params": params,
            "time": cmd["time"],
        }

    def _extract_players_from_text(self, text: str) -> Optional[dict]:
        count_m = re.search(r'"count"\s*:\s*(\d+)', text)
        ts_m = re.search(r'"timestamp"\s*:\s*(\d+)', text)
        players: List[Dict[str, Any]] = []
        for obj_m in re.finditer(r'\{[^{}]*?"name"\s*:\s*"([^"]*)"[^{}]*?\}', text):
            chunk = obj_m.group(0)
            name_m = re.search(r'"name"\s*:\s*"([^"]*)"', chunk)
            role_m = re.search(r'"role"\s*:\s*"([^"]*)"', chunk)
            role_id_m = re.search(r'"role_id"\s*:\s*"([^"]*)"', chunk)
            idx_m = re.search(r'"index"\s*:\s*(\d+)', chunk)
            thrall_m = re.search(r'"is_thrall"\s*:\s*(true|false)', chunk, re.IGNORECASE)
            pawn_m = re.search(r'"has_pawn"\s*:\s*(true|false)', chunk, re.IGNORECASE)
            dead_m = re.search(r'"is_dead"\s*:\s*(true|false)', chunk, re.IGNORECASE)

            name = name_m.group(1) if name_m else ""
            role = role_m.group(1) if role_m else ""
            role_id = role_id_m.group(1) if role_id_m else ""
            idx = int(idx_m.group(1)) if idx_m else len(players)
            is_thrall = (thrall_m.group(1).lower() == "true") if thrall_m else False
            player = {
                "name": name,
                "role": role,
                "role_id": role_id,
                "index": idx,
                "is_thrall": is_thrall,
                "has_pawn": (pawn_m.group(1).lower() == "true") if pawn_m else False,
                "is_dead": (dead_m.group(1).lower() == "true") if dead_m else False,
            }
            for key in ("x", "y", "z"):
                coord_m = re.search(r'"%s"\s*:\s*(-?\d+(?:\.\d+)?)' % key, chunk)
                player[key] = float(coord_m.group(1)) if coord_m else None
            players.append(player)
        if not players and not count_m:
            return None
        result: Dict[str, Any] = {
            "count": int(count_m.group(1)) if count_m else len(players),
            "players": players,
        }
        if ts_m:
            result["timestamp"] = int(ts_m.group(1))
        return result

    def _recent_player_identities(self) -> Dict[str, Dict[str, str]]:
        try:
            with self.game_log_path.open("rb") as log_file:
                size = self.game_log_path.stat().st_size
                log_file.seek(max(0, size - 8 * 1024 * 1024))
                text = log_file.read().decode("utf-8", "replace")
        except OSError:
            return {}

        identities: Dict[str, Dict[str, str]] = {}
        for match in LOGIN_PATTERN.finditer(text):
            name = html.unescape(match.group("name")).strip()
            identity = split_player_user_id(match.group("uid"))
            if not identity["user_id"]:
                continue
            identity.update({"name": name, "platform": match.group("platform") or "EOSPlus"})
            identities[normalize_player_name(name)] = identity
        return identities

    def _read_blacklist_unlocked(self) -> Dict[str, Any]:
        data = read_json(self.blacklist_path, None)
        if not isinstance(data, dict):
            return {"version": 1, "updated_at": "", "entries": []}
        entries = data.get("entries")
        if not isinstance(entries, list):
            entries = []
        clean_entries = [item for item in entries if isinstance(item, dict) and item.get("user_id")]
        return {
            "version": 1,
            "updated_at": str(data.get("updated_at") or ""),
            "entries": clean_entries,
        }

    def get_blacklist(self) -> Dict[str, Any]:
        with self.blacklist_lock:
            data = self._read_blacklist_unlocked()
        entries = sorted(data["entries"], key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return {
            "ok": True,
            "version": 1,
            "updated_at": data["updated_at"],
            "count": len(entries),
            "reason_presets": BLACKLIST_REASON_PRESETS,
            "check_token": self.blacklist_check_token,
            "entries": entries,
        }

    @staticmethod
    def _entry_identity_keys(entry: Dict[str, Any]) -> set:
        return {
            str(entry.get(key) or "").strip().casefold()
            for key in ("user_id", "steam_id", "eos_id")
            if str(entry.get(key) or "").strip()
        }

    def _find_blacklist_entry(self, identity: Dict[str, Any], entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        wanted = self._entry_identity_keys(identity)
        if not wanted:
            return None
        for entry in entries:
            if wanted.intersection(self._entry_identity_keys(entry)):
                return entry
        return None

    def add_blacklist(self, params: Dict[str, Any]) -> Dict[str, Any]:
        player_name = html.unescape(str(params.get("player") or "")).strip()
        if not player_name:
            raise ValueError("请填写玩家名称" if params.get("manual") is True else "请选择在线玩家")
        if len(player_name) > 80:
            raise ValueError("玩家名称最多 80 个字符")
        if any(ord(char) < 32 or ord(char) == 127 for char in player_name):
            raise ValueError("玩家名称不能包含控制字符")

        reason_code = str(params.get("reason_code") or "other").strip()
        custom_reason = str(params.get("reason") or "").strip()
        if len(custom_reason) > 200:
            raise ValueError("黑名单理由最多 200 个字符")
        preset_reason = BLACKLIST_REASON_PRESETS.get(reason_code, "")
        reason = custom_reason or preset_reason
        if not reason:
            raise ValueError("请选择预设理由或填写自定义理由")

        if params.get("manual") is True:
            identity = manual_blacklist_identity(params)
            target = {"platform": identity["platform"]}
        else:
            players = self.get_players().get("players", [])
            target = next(
                (item for item in players if normalize_player_name(item.get("name")) == normalize_player_name(player_name)),
                None,
            )
            if not target:
                raise ValueError("未找到在线玩家：%s" % player_name)
            if not target.get("user_id"):
                raise ValueError("暂未从登录日志读取到该玩家的 Steam/EOS ID，请刷新后重试")
            identity = split_player_user_id(target.get("user_id"))

        now = now_text()
        with self.blacklist_lock:
            data = self._read_blacklist_unlocked()
            incoming_keys = self._entry_identity_keys(identity)
            existing_entries = [
                item for item in data["entries"]
                if incoming_keys.intersection(self._entry_identity_keys(item))
            ]
            steam_ids = {
                value for value in [identity.get("steam_id")] + [item.get("steam_id") for item in existing_entries]
                if value
            }
            eos_ids = {
                str(value).lower() for value in [identity.get("eos_id")] + [item.get("eos_id") for item in existing_entries]
                if value
            }
            if len(steam_ids) > 1 or len(eos_ids) > 1:
                raise ValueError("该身份与已有黑名单记录冲突，请先检查 Steam/EOS ID")
            steam_id = next(iter(steam_ids), "")
            eos_id = next(iter(eos_ids), "")
            user_id = "%s_+_|%s" % (steam_id, eos_id) if steam_id and eos_id else (
                steam_id or eos_id or identity["user_id"]
            )
            aliases = []
            created_at = now
            created_values = [str(item.get("created_at") or "") for item in existing_entries if item.get("created_at")]
            if created_values:
                created_at = min(created_values)
            for existing in existing_entries:
                aliases.extend(str(item) for item in existing.get("aliases", []) if str(item).strip())
                old_name = str(existing.get("name") or "").strip()
                if old_name and normalize_player_name(old_name) != normalize_player_name(player_name):
                    aliases.append(old_name)
                data["entries"].remove(existing)
            aliases = list(dict.fromkeys(aliases))[-10:]
            entry = {
                "name": player_name,
                "user_id": user_id,
                "steam_id": steam_id,
                "eos_id": eos_id,
                "platform": "EOSPlus" if steam_id and eos_id else str(target.get("platform") or ("Steam" if steam_id else "EOS")),
                "reason_code": reason_code if reason_code in BLACKLIST_REASON_PRESETS else "other",
                "reason": reason,
                "aliases": aliases,
                "created_at": created_at,
                "updated_at": now,
            }
            data["entries"].append(entry)
            data["updated_at"] = now
            atomic_write_json(self.blacklist_path, data)
        return {"ok": True, "message": "已加入黑名单", "entry": entry}

    def remove_blacklist(self, params: Dict[str, Any]) -> Dict[str, Any]:
        identity = split_player_user_id(params.get("user_id") or params.get("steam_id"))
        if not identity["user_id"]:
            raise ValueError("缺少要移除的用户 ID")
        with self.blacklist_lock:
            data = self._read_blacklist_unlocked()
            target = self._find_blacklist_entry(identity, data["entries"])
            if not target:
                raise ValueError("黑名单中未找到该用户")
            data["entries"].remove(target)
            data["updated_at"] = now_text()
            atomic_write_json(self.blacklist_path, data)
        return {"ok": True, "message": "已移出黑名单", "entry": target}

    def update_blacklist(self, params: Dict[str, Any]) -> Dict[str, Any]:
        identity = split_player_user_id(params.get("user_id") or params.get("steam_id"))
        if not identity["user_id"]:
            raise ValueError("缺少要修改的用户 ID")

        reason_code = str(params.get("reason_code") or "other").strip()
        custom_reason = str(params.get("reason") or "").strip()
        if len(custom_reason) > 200:
            raise ValueError("黑名单理由最多 200 个字符")
        reason = custom_reason or BLACKLIST_REASON_PRESETS.get(reason_code, "")
        if not reason:
            raise ValueError("请选择预设理由或填写自定义理由")

        new_name = html.unescape(str(params.get("name") or "")).strip()
        if len(new_name) > 80:
            raise ValueError("玩家名称最多 80 个字符")

        with self.blacklist_lock:
            data = self._read_blacklist_unlocked()
            target = self._find_blacklist_entry(identity, data["entries"])
            if not target:
                raise ValueError("黑名单中未找到该用户")
            old_name = str(target.get("name") or "").strip()
            aliases = [str(item) for item in target.get("aliases", []) if str(item).strip()]
            if new_name and old_name and normalize_player_name(new_name) != normalize_player_name(old_name):
                aliases.append(old_name)
                target["name"] = new_name
            target["aliases"] = list(dict.fromkeys(aliases))[-10:]
            target["reason_code"] = reason_code if reason_code in BLACKLIST_REASON_PRESETS else "other"
            target["reason"] = reason
            target["updated_at"] = now_text()
            data["updated_at"] = target["updated_at"]
            atomic_write_json(self.blacklist_path, data)
            updated = dict(target)
        return {"ok": True, "message": "黑名单记录已更新", "entry": updated}

    def check_lobby_blacklist(self) -> Dict[str, Any]:
        blacklist = self.get_blacklist()
        result = self.get_players()
        matches = []
        for player in result.get("players", []):
            entry = self._find_blacklist_entry(player, blacklist["entries"])
            if entry:
                matches.append({
                    "name": player.get("name") or entry.get("name") or "未知玩家",
                    "user_id": player.get("user_id") or entry.get("user_id") or "",
                    "steam_id": player.get("steam_id") or entry.get("steam_id") or "",
                    "reason": entry.get("reason") or "未填写",
                    "reason_code": entry.get("reason_code") or "other",
                    "blacklisted_at": entry.get("created_at") or "",
                })
        return {
            "ok": True,
            "checked_at": now_text(),
            "lobby_stale": bool(result.get("stale", True)),
            "player_count": len(result.get("players", [])),
            "match_count": len(matches),
            "matches": matches,
        }

    def check_blacklist_preflight(self, params: Dict[str, Any]) -> Dict[str, Any]:
        identity = split_player_user_id(params.get("user_id") or params.get("steam_id"))
        blacklist = self.get_blacklist()
        local_match = self._find_blacklist_entry(identity, blacklist["entries"]) if identity["user_id"] else None
        lobby_check = self.check_lobby_blacklist()
        return {
            "ok": True,
            "local_identity_available": bool(identity["user_id"]),
            "local_match": local_match,
            "lobby_match_count": lobby_check.get("match_count", 0),
            "lobby_matches": lobby_check.get("matches", []),
            "checked_at": now_text(),
        }

    def get_players(self) -> dict:
        result = None
        for _ in range(3):
            data = read_json(self.player_list_path, None)
            if isinstance(data, dict) and "players" in data:
                result = data
                break
            try:
                text = self.player_list_path.read_text(encoding="utf-8", errors="replace")
                if text.strip():
                    partial = self._extract_players_from_text(text)
                    if partial is not None:
                        result = partial
                        break
            except OSError:
                pass
            time.sleep(0.3)
        if result is None:
            result = {"count": 0, "players": []}
        try:
            mtime = self.player_list_path.stat().st_mtime
            result["stale"] = (time.time() - mtime) > 5
            result["file_mtime"] = int(mtime)
        except OSError:
            result["stale"] = True
        identities = self._recent_player_identities()
        blacklist_entries = self.get_blacklist()["entries"]
        for player in result.get("players", []):
            player["is_thrall"] = bool(player.get("is_thrall"))
            identity = identities.get(normalize_player_name(player.get("name")))
            if identity:
                player.update(identity)
            else:
                player.update({"user_id": "", "steam_id": "", "eos_id": "", "platform": ""})
            entry = self._find_blacklist_entry(player, blacklist_entries)
            player["blacklisted"] = bool(entry)
            player["blacklist_reason"] = str(entry.get("reason") or "") if entry else ""
        return result

    def get_thralls(self) -> dict:
        data = self.get_players()
        players = data.get("players", [])
        thralls = [p for p in players if p.get("is_thrall") is True]
        explorers = [p for p in players if not p.get("is_thrall")]
        return {
            "ok": True,
            "stale": data.get("stale", False),
            "count": len(thralls),
            "total_players": len(players),
            "thralls": thralls,
            "explorers": explorers,
            "timestamp": data.get("timestamp"),
        }



def app_html() -> str:
    return r'''<!doctype html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dread Hunger Linux GM 控制台</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/element-plus@2.8.0/dist/index.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/element-plus@2.8.0/theme-chalk/dark/css-vars.css">
  <script src="https://cdn.jsdelivr.net/npm/vue@3.4.38/dist/vue.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/element-plus@2.8.0/dist/index.full.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/@element-plus/icons-vue@2.3.1/dist/index.iife.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/element-plus@2.8.0/dist/locale/zh-cn.min.js"></script>
  <style>
    html.dark {
      --el-bg-color: #070c14;
      --el-bg-color-overlay: #0f1926;
      --el-bg-color-page: #070c14;
      --el-fill-color-blank: #0c141f;
      --el-fill-color: #162436;
      --el-fill-color-light: #121e2d;
      --el-border-color: #1a2c42;
      --el-border-color-light: #1a2c42;
      --el-border-color-lighter: #142232;
      --el-text-color-primary: #e2ebf3;
      --el-text-color-regular: #cbd5e1;
      --el-text-color-secondary: #8fa7b8;
    }
    :root {
      --bg-dark: #070c14;
      --card-dark: #0f1926;
      --border-color: #1a2c42;
      --text-main: #e2ebf3;
      --text-sub: #8fa7b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-dark);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      min-height: 100vh;
      overflow-x: hidden;
    }
    [v-cloak] { display: none !important; }

    .el-tabs--border-card {
      background: #0b131e !important;
      border: 1px solid #1a2c42 !important;
      border-radius: 8px !important;
      overflow: hidden;
    }
    .el-tabs--border-card > .el-tabs__header {
      background-color: #070c14 !important;
      border-bottom: 1px solid #1a2c42 !important;
      margin: 0;
    }
    .el-tabs--border-card > .el-tabs__header .el-tabs__item {
      color: #8fa7b8 !important;
      border: none !important;
      border-right: 1px solid #142232 !important;
      transition: all 0.2s;
    }
    .el-tabs--border-card > .el-tabs__header .el-tabs__item:hover {
      color: #38bdf8 !important;
      background: #0f1926 !important;
    }
    .el-tabs--border-card > .el-tabs__header .el-tabs__item.is-active {
      color: #38bdf8 !important;
      background-color: #0b131e !important;
      border-right-color: #1a2c42 !important;
      border-left-color: #1a2c42 !important;
      font-weight: 600;
    }
    .el-tabs--border-card > .el-tabs__content {
      padding: 18px !important;
      background: #0b131e !important;
      color: #e2ebf3 !important;
    }
    
    .el-input__wrapper, .el-textarea__inner {
      background-color: #070c14 !important;
      box-shadow: 0 0 0 1px #1a2c42 inset !important;
      color: #e2ebf3 !important;
    }
    .el-input__wrapper:hover, .el-textarea__inner:hover {
      box-shadow: 0 0 0 1px #38bdf8 inset !important;
    }
    .el-input__wrapper.is-focus, .el-textarea__inner:focus {
      box-shadow: 0 0 0 1px #0284c7 inset !important;
    }
    .el-select__wrapper {
      background-color: #070c14 !important;
      box-shadow: 0 0 0 1px #1a2c42 inset !important;
      color: #e2ebf3 !important;
    }
    .el-radio-button__inner {
      background: #070c14 !important;
      color: #8fa7b8 !important;
      border: 1px solid #1a2c42 !important;
    }
    .el-radio-button__original-radio:checked + .el-radio-button__inner {
      background-color: #0284c7 !important;
      border-color: #0284c7 !important;
      color: #ffffff !important;
      box-shadow: -1px 0 0 0 #0284c7 !important;
    }
    .el-message-box, .el-dialog {
      background: #0f1926 !important;
      border: 1px solid #1a2c42 !important;
      color: #e2ebf3 !important;
    }
    .el-message-box__title, .el-dialog__title {
      color: #f1f5f9 !important;
    }
    .el-message-box__message {
      color: #cbd5e1 !important;
    }

    .login-wrapper {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #060a10;
      background-image: 
        radial-gradient(ellipse at 20% 30%, rgba(14, 165, 233, 0.15) 0%, transparent 55%),
        radial-gradient(ellipse at 80% 70%, rgba(99, 102, 241, 0.12) 0%, transparent 55%),
        radial-gradient(circle at 50% 50%, rgba(15, 23, 42, 0.7) 0%, #060a10 100%);
      padding: 24px;
      position: relative;
    }
    .login-card {
      width: 100%;
      max-width: 440px;
      background: rgba(15, 25, 38, 0.92);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(56, 189, 248, 0.25);
      border-radius: 16px;
      padding: 42px 36px;
      box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.8), 0 0 35px rgba(14, 165, 233, 0.15);
      animation: fadeIn 0.35s ease-out;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(14px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .login-header {
      text-align: center;
      margin-bottom: 28px;
    }
    .login-icon-box {
      width: 68px;
      height: 68px;
      border-radius: 18px;
      background: linear-gradient(135deg, rgba(14, 165, 233, 0.25), rgba(99, 102, 241, 0.2));
      border: 1px solid rgba(56, 189, 248, 0.35);
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 16px;
      box-shadow: 0 0 24px rgba(14, 165, 233, 0.3);
    }
    .login-header h2 {
      font-size: 22px;
      font-weight: 700;
      color: #f1f5f9;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
    }
    .login-sub {
      color: #8fa7b8;
      font-size: 13px;
    }
    .form-label {
      display: block;
      font-size: 13px;
      color: #94a3b8;
      margin-bottom: 8px;
      font-weight: 500;
    }
    .login-submit-btn {
      width: 100%;
      margin-top: 24px;
      height: 44px;
      font-size: 15px;
      font-weight: 600;
      letter-spacing: 1px;
      background: linear-gradient(135deg, #0284c7, #4f46e5) !important;
      border: none !important;
      border-radius: 8px !important;
      box-shadow: 0 4px 16px rgba(14, 165, 233, 0.35);
      transition: all 0.2s;
    }
    .login-submit-btn:hover {
      opacity: 0.92;
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(14, 165, 233, 0.45);
    }
    .login-footer-tips {
      margin-top: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      font-size: 12px;
      color: #64748b;
    }
    .login-footer-tips code {
      color: #38bdf8;
      background: rgba(14, 165, 233, 0.1);
      padding: 2px 6px;
      border-radius: 4px;
    }

    .dashboard-wrapper {
      max-width: 1280px;
      margin: 0 auto;
      padding: 16px 20px 40px;
      animation: fadeIn 0.3s ease-out;
    }
    .el-card {
      background-color: var(--card-dark) !important;
      border: 1px solid var(--border-color) !important;
      border-radius: 8px !important;
      margin-bottom: 16px;
    }
    .el-card__header {
      border-bottom: 1px solid var(--border-color) !important;
      padding: 12px 18px !important;
    }
    .top-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding: 12px 18px;
      background: linear-gradient(90deg, #132236 0%, #0d1826 100%);
      border: 1px solid #1f354f;
      border-radius: 8px;
      flex-wrap: wrap;
      gap: 10px;
    }
    .brand-title {
      font-size: 18px;
      font-weight: 700;
      color: #409EFF;
      display: flex;
      align-items: center;
      gap: 8px;
      letter-spacing: 0.5px;
    }
    .player-card-list {
      max-height: 280px;
      overflow-y: auto;
    }
    .player-item-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 12px;
      border-radius: 6px;
      background: #0c141f;
      margin-bottom: 6px;
      border: 1px solid #162436;
      transition: all 0.2s;
      cursor: pointer;
    }
    .player-item-row:hover {
      background: #152538;
      border-color: #409EFF;
    }
    .player-item-row.is-thrall-row {
      border-color: rgba(245, 108, 108, 0.4);
      background: linear-gradient(90deg, rgba(245, 108, 108, 0.12) 0%, #0c141f 100%);
    }
    .player-item-row.is-thrall-row:hover {
      border-color: #f56c6c;
      background: linear-gradient(90deg, rgba(245, 108, 108, 0.22) 0%, #152538 100%);
    }
    .player-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #67C23A;
      display: inline-block;
      margin-right: 6px;
      box-shadow: 0 0 6px rgba(103,194,58,0.6);
    }
    .player-status-dot.thrall-dot {
      background: #f56c6c;
      box-shadow: 0 0 6px rgba(245,108,108,0.85);
    }
    .thrall-hero-banner {
      padding: 14px 18px;
      border-radius: 8px;
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }
    .thrall-hero-banner.has-thralls {
      background: linear-gradient(135deg, rgba(245, 108, 108, 0.18) 0%, rgba(20, 10, 24, 0.85) 100%);
      border: 1px solid rgba(245, 108, 108, 0.38);
    }
    .thrall-hero-banner.no-thralls {
      background: #0c141f;
      border: 1px solid #1a2c42;
    }
    .thrall-card {
      background: linear-gradient(135deg, rgba(245, 108, 108, 0.12) 0%, rgba(15, 25, 38, 0.95) 100%);
      border: 1px solid rgba(245, 108, 108, 0.35);
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 12px;
      transition: all 0.2s;
      position: relative;
      overflow: hidden;
    }
    .thrall-card:hover {
      border-color: #f56c6c;
      box-shadow: 0 4px 20px rgba(245, 108, 108, 0.25);
    }
    .thrall-card::after {
      content: "THRALL";
      position: absolute;
      right: 12px;
      bottom: -8px;
      font-size: 36px;
      font-weight: 900;
      color: rgba(245, 108, 108, 0.06);
      pointer-events: none;
      letter-spacing: 2px;
    }
    .explorer-card {
      background: #0c141f;
      border: 1px solid #1a2c42;
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: all 0.2s;
    }
    .explorer-card:hover {
      border-color: #38bdf8;
      background: #101c2c;
    }
    .result-console {
      background: #060a10;
      color: #9feaf9;
      font-family: 'Cascadia Code', Consolas, Monaco, monospace;
      font-size: 12.5px;
      padding: 12px;
      border-radius: 6px;
      border: 1px solid #142130;
      min-height: 90px;
      max-height: 220px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .preset-tag {
      cursor: pointer;
      margin-right: 6px;
      margin-bottom: 6px;
    }
  </style>
</head>
<body class="dark">
<div id="app" v-cloak>
  <div v-if="!isLoggedIn" class="login-wrapper">
    <div class="login-card">
      <div class="login-header">
        <div class="login-icon-box">
          <el-icon :size="36" color="#38bdf8"><Compass /></el-icon>
        </div>
        <h2>Dread Hunger GM 控制台</h2>
        <p class="login-sub">Linux 游戏服务器 GM 运维管理中控</p>
      </div>

      <div class="login-form">
        <div style="margin-bottom: 18px">
          <label class="form-label">管理员密码 (Access Password)</label>
          <el-input
            v-model="loginPwd"
            type="password"
            size="large"
            placeholder="请输入 GM 登录密码"
            show-password
            :prefix-icon="Key"
            @keyup.enter="doLogin"
            autofocus
          />
        </div>

        <el-button
          type="primary"
          size="large"
          :icon="Check"
          :loading="isLoggingIn"
          class="login-submit-btn"
          @click="doLogin"
        >
          登 录 控 制 台
        </el-button>
      </div>
    </div>
  </div>

  <div v-else class="dashboard-wrapper">
    <div class="top-header">
      <div class="brand-title">
        <el-icon :size="20"><Compass /></el-icon>
        <span>Dread Hunger Linux GM 控制台</span>
        <el-tag size="small" type="primary" effect="dark">v''' + VERSION + r'''</el-tag>
      </div>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <el-tag size="small" :type="thrallList.length > 0 ? 'danger' : 'info'" effect="dark" style="cursor:pointer;font-weight:700" @click="activeTab = 'thralls'">
          🩸 狼人: {{ thrallList.length }} 人
        </el-tag>
        <el-tag size="small" :type="playerState.count > 0 ? 'success' : 'info'" effect="dark">
          <el-icon style="vertical-align:middle;margin-right:2px"><User /></el-icon>
          在线玩家: {{ playerState.count }} 人
        </el-tag>
        <el-tag size="small" :type="playerState.stale ? 'warning' : 'success'" effect="plain">
          {{ playerState.stale ? 'Frida 离线/未开始' : 'Frida 状态正常' }}
        </el-tag>
        <el-button size="small" :type="thrallList.length > 0 ? 'danger' : 'default'" :plain="thrallList.length === 0" :icon="View" @click="activeTab = 'thralls'">查看狼人名单</el-button>
        <el-button size="small" type="primary" plain :icon="List" @click="openBlacklistCenter">黑名单中心</el-button>
        <el-button size="small" :icon="Refresh" @click="fetchPlayers" :loading="isRefreshing">刷新</el-button>
        <el-button size="small" type="danger" plain :icon="SwitchButton" @click="doLogout">退出登录</el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :sm="24" :md="8" :lg="8">
        <el-card shadow="hover">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <div style="display:flex;align-items:center;gap:6px;font-weight:600">
                <el-icon color="#409EFF"><UserFilled /></el-icon>
                <span>实时在线玩家</span>
              </div>
              <div style="display:flex;align-items:center;gap:4px">
                <el-tag size="small" :type="thrallList.length > 0 ? 'danger' : 'info'" effect="dark">
                  🩸 {{ thrallList.length }} 狼
                </el-tag>
                <el-tag size="small" type="info">{{ playerList.length }} 人</el-tag>
              </div>
            </div>
            <div style="margin-top:10px">
              <el-radio-group v-model="playerFilter" size="small" style="width:100%;display:flex">
                <el-radio-button label="all" style="flex:1">全部 ({{ playerList.length }})</el-radio-button>
                <el-radio-button label="thralls" style="flex:1">🩸 狼人 ({{ thrallList.length }})</el-radio-button>
                <el-radio-button label="explorers" style="flex:1">🚢 好人 ({{ explorerList.length }})</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div v-if="filteredPlayerList.length === 0" style="text-align:center;padding:24px 0;color:#8fa7b8;font-size:13px">
            <el-empty :description="playerFilter === 'thralls' ? '当前无狼人玩家（尚未发牌或全员好人）' : (playerFilter === 'explorers' ? '当前无好人玩家' : '暂无玩家在线或对局未开始')" :image-size="60" />
          </div>
          <div v-else class="player-card-list">
            <div
              v-for="p in filteredPlayerList"
              :key="p.index"
              class="player-item-row"
              :class="{ 'is-thrall-row': p.is_thrall }"
              @click="quickSelectPlayer(p.name)"
            >
              <div style="min-width:0;flex:1">
                <div style="display:flex;align-items:center;gap:6px">
                  <span class="player-status-dot" :class="{ 'thrall-dot': p.is_thrall }"></span>
                  <strong style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :style="{ color: p.is_thrall ? '#ff7875' : '#e2ebf3' }">{{ p.name }}</strong>
                  <el-tag size="small" type="danger" effect="dark" v-if="p.is_thrall" style="font-weight:700">🩸 狼人</el-tag>
                  <el-tag size="small" type="success" effect="plain" v-if="p.role">{{ p.role }}</el-tag>
                  <el-tag size="small" type="danger" effect="dark" v-if="p.blacklisted">黑名单</el-tag>
                  <el-tag size="small" type="warning" effect="plain" v-if="p.is_dead">已死亡</el-tag>
                </div>
                <div style="font-size:11px;color:#8fa7b8;margin:4px 0 0 14px;font-family:Consolas,monospace">
                  {{ p.has_pawn ? ('X ' + formatCoord(p.x) + ' · Y ' + formatCoord(p.y) + ' · Z ' + formatCoord(p.z)) : '暂无角色坐标' }}
                </div>
              </div>
              <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
                <span v-if="p.steam_id" style="font-size:11px;color:#8fa7b8">{{ p.steam_id }}</span>
                <el-tag size="small" type="info">#{{ p.index }}</el-tag>
                <el-button size="small" type="primary" link @click.stop="quickSelectPlayer(p.name)">选中</el-button>
              </div>
            </div>
          </div>
          <div style="margin-top:10px;font-size:11.5px;color:#8fa7b8;display:flex;align-items:center;gap:4px">
            <el-icon><InfoFilled /></el-icon> 点击玩家即可快速填入右侧操作表单
          </div>
        </el-card>

        <el-card shadow="hover">
          <template #header>
            <div style="display:flex;align-items:center;gap:6px;font-weight:600">
              <el-icon color="#E6A23C"><Tickets /></el-icon>
              <span>GM 运作机制</span>
            </div>
          </template>
          <div style="font-size:12.5px;color:#8fa7b8;line-height:1.7">
            <p>• 控制台将指令安全写入 <code>gm_commands.json</code></p>
            <p>• 服务端 <code>GM控制台_Linux.js</code> Frida 插件每秒自动轮询并无缝执行指令</p>
            <p>• 坐标与玩家状态每秒刷新，原生动作会回传真实执行结果</p>
            <p>• 支持消息、判胜、开库、踢人、复活、传送、发物品及处决</p>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="24" :md="16" :lg="16">
        <el-card shadow="hover">
          <template #header>
            <div style="display:flex;align-items:center;gap:6px;font-weight:600">
              <el-icon color="#67C23A"><Operation /></el-icon>
              <span>GM 功能操作面板</span>
            </div>
          </template>

          <el-tabs v-model="activeTab" type="border-card">
            <el-tab-pane name="thralls">
              <template #label>
                <span>
                  <el-icon style="vertical-align:middle;margin-right:2px;color:#f56c6c"><View /></el-icon>
                  <span style="color:#f56c6c;font-weight:700">狼人名单</span>
                  <el-badge v-if="thrallList.length > 0" :value="thrallList.length" type="danger" style="margin-left:4px" />
                </span>
              </template>

              <div style="padding:4px 0">
                <div v-if="thrallList.length > 0" class="thrall-hero-banner has-thralls">
                  <div style="display:flex;align-items:center;gap:12px">
                    <span style="font-size:26px">🩸</span>
                    <div>
                      <div style="font-size:15px;font-weight:700;color:#ff7875">本局已识别 {{ thrallList.length }} 名狼人 (内奸)</div>
                      <div style="font-size:12px;color:#cbd5e1;margin-top:2px">数据实时自服务端内存 <code>ADH_PlayerState::bIsThrall</code> 同步</div>
                    </div>
                  </div>
                  <div style="display:flex;gap:8px">
                    <el-button size="small" type="danger" plain :icon="Refresh" @click="fetchPlayers">刷新阵营</el-button>
                  </div>
                </div>

                <div v-else class="thrall-hero-banner no-thralls">
                  <div style="display:flex;align-items:center;gap:10px">
                    <el-icon :size="20" color="#8fa7b8"><InfoFilled /></el-icon>
                    <div>
                      <div style="font-size:14px;font-weight:600;color:#cbd5e1">当前尚未检测到狼人身份</div>
                      <div style="font-size:12px;color:#8fa7b8;margin-top:2px">可能处于大厅打牌选人阶段，或对局尚未正式发牌。进入暴风雪航行后将自动识别。</div>
                    </div>
                  </div>
                  <el-button size="small" :icon="Refresh" @click="fetchPlayers">手动刷新</el-button>
                </div>

                <div v-if="thrallList.length > 0">
                  <div style="font-size:13px;font-weight:700;color:#ff7875;margin-bottom:12px;display:flex;align-items:center;gap:6px">
                    <span>🩸 狼人阵容 (共 {{ thrallList.length }} 人)</span>
                  </div>
                  <div v-for="t in thrallList" :key="t.index" class="thrall-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
                      <div>
                        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                          <span style="font-size:17px;font-weight:800;color:#ffffff">{{ t.name }}</span>
                          <el-tag size="small" type="danger" effect="dark" style="font-weight:700">🩸 狼人 (内奸)</el-tag>
                          <el-tag size="small" type="success" effect="plain" v-if="t.role">{{ t.role }}</el-tag>
                          <el-tag size="small" type="danger" effect="dark" v-if="t.blacklisted">黑名单</el-tag>
                          <el-tag size="small" type="info">座位 #{{ t.index }}</el-tag>
                        </div>
                        <div style="margin-top:8px;font-size:12px;color:#8fa7b8;display:flex;gap:14px;flex-wrap:wrap">
                          <span v-if="t.steam_id">Steam ID: <code style="color:#38bdf8">{{ t.steam_id }}</code></span>
                          <span v-if="t.eos_id">EOS ID: <code style="color:#cbd5e1">{{ t.eos_id.slice(0, 8) }}...</code></span>
                        </div>
                      </div>
                      <div style="display:flex;gap:6px;flex-wrap:wrap">
                        <el-button size="small" type="primary" plain @click="quickSelectPlayer(t.name)">选中此人</el-button>
                        <el-button size="small" type="warning" plain @click="quickTeleportPlayer(t.name)">传回船</el-button>
                        <el-button size="small" type="success" plain @click="quickRevivePlayer(t.name)">复活</el-button>
                        <el-button size="small" type="danger" plain @click="quickKickPlayer(t.name)">踢出</el-button>
                      </div>
                    </div>
                  </div>
                </div>

                <div style="margin-top:16px">
                  <div style="border:1px solid #1a2c42;background:#0c141f;border-radius:8px;padding:12px 14px">
                    <div style="font-size:13px;font-weight:600;color:#38bdf8;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center">
                      <span>🚢 好人探险者阵容 (共 {{ explorerList.length }} 人)</span>
                    </div>
                    <div v-if="explorerList.length === 0" style="padding:10px 0;color:#8fa7b8;font-size:12px;text-align:center">
                      暂无好人数据
                    </div>
                    <div v-else style="display:grid;grid-template-columns:repeat(auto-fill, minmax(240px, 1fr));gap:8px">
                      <div v-for="exp in explorerList" :key="exp.index" class="explorer-card">
                        <div style="min-width:0;flex:1">
                          <div style="display:flex;align-items:center;gap:6px">
                            <span style="font-weight:600;color:#e2ebf3;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ exp.name }}</span>
                            <el-tag size="small" type="success" effect="plain" v-if="exp.role">{{ exp.role }}</el-tag>
                            <el-tag size="small" type="info">#{{ exp.index }}</el-tag>
                          </div>
                          <div v-if="exp.steam_id" style="font-size:11px;color:#8fa7b8;margin-top:3px">
                            Steam: {{ exp.steam_id }}
                          </div>
                        </div>
                        <el-button size="small" type="primary" link @click="quickSelectPlayer(exp.name)">选中</el-button>
                      </div>
                    </div>
                  </div>
                </div>

                <div style="margin-top:16px;padding:14px 16px;border:1px solid #1a2c42;background:#0c141f;border-radius:8px">
                  <div style="font-size:13px;font-weight:600;margin-bottom:10px;color:#e2ebf3">⚡ 阵营对局快捷控制</div>
                  <div style="display:flex;gap:10px;flex-wrap:wrap">
                    <el-button type="success" :icon="Trophy" @click="directEndGame(1)">判定好人探险者胜利</el-button>
                    <el-button type="danger" :icon="CircleCloseFilled" @click="directEndGame(2)">判定狼人内奸胜利</el-button>
                    <el-button type="primary" :icon="Promotion" @click="confirmSkipPoker">跳过打牌并开始游戏</el-button>
                    <el-button type="warning" :icon="Unlock" @click="submitAction('open_armory', {})">开启军械库</el-button>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane name="msg">
              <template #label>
                <span><el-icon style="vertical-align:middle;margin-right:2px"><ChatDotRound /></el-icon> 发送消息</span>
              </template>
              <el-form label-position="top" size="small">
                <el-form-item label="目标接收人">
                  <el-select v-model="formMsg.player" placeholder="选择目标玩家" style="width:100%">
                    <el-option label="📢 全部玩家 (全服广播)" value="all" />
                    <el-option v-for="p in playerList" :key="p.index" :label="p.name + (p.role ? ' ' + p.role : '') + ' #' + p.index" :value="p.name" />
                  </el-select>
                </el-form-item>
                <el-form-item label="消息预设模板">
                  <div>
                    <el-tag class="preset-tag" @click="formMsg.message = '[系统公告] 服务器将在 5 分钟后进行维护重启，请各位玩家注意！'">[维护公告]</el-tag>
                    <el-tag class="preset-tag" type="warning" @click="formMsg.message = '[警告] 严禁任何利用外挂作弊与卡 Bug 行为，违者直接封禁！'">[严禁作弊]</el-tag>
                    <el-tag class="preset-tag" type="success" @click="formMsg.message = '[提示] 暴风雪即将来临，请所有人尽快做好防寒准备！'">[防寒提示]</el-tag>
                  </div>
                </el-form-item>
                <el-form-item label="消息内容">
                  <el-input v-model="formMsg.message" type="textarea" :rows="3" placeholder="输入要发送给玩家的消息文本..." />
                </el-form-item>
                <el-button type="primary" :icon="Promotion" :loading="isSubmitting" @click="submitAction('send_message', formMsg)">发送消息</el-button>
              </el-form>
            </el-tab-pane>

            <el-tab-pane name="end">
              <template #label>
                <span><el-icon style="vertical-align:middle;margin-right:2px"><Trophy /></el-icon> 结束游戏</span>
              </template>
              <div style="padding:10px 0">
                <p style="color:#8fa7b8;font-size:13px;margin-bottom:14px">强制结束当前对局并结算比赛结果，请选择获胜阵营：</p>
                <el-radio-group v-model="formEnd.team" size="large" style="margin-bottom:18px">
                  <el-radio-button :label="1">🚢 探险者好人胜利 (Explorers)</el-radio-button>
                  <el-radio-button :label="2">🩸 叛徒内奸胜利 (Thralls)</el-radio-button>
                </el-radio-group>
                <div>
                  <el-button type="danger" :icon="CircleCloseFilled" :loading="isSubmitting" @click="confirmEndGame">强制结束对局</el-button>
                </div>
                <el-divider content-position="left">打牌阶段控制</el-divider>
                <el-alert title="跳过后由服务端立即结束牌局、随机分配狼人并进入正式游戏。" type="warning" :closable="false" style="margin-bottom:14px" />
                <el-button type="primary" :icon="Promotion" :loading="isSubmitting" @click="confirmSkipPoker">跳过打牌并开始游戏</el-button>
              </div>
            </el-tab-pane>

            <el-tab-pane name="armory">
              <template #label>
                <span><el-icon style="vertical-align:middle;margin-right:2px"><Key /></el-icon> 开启军械库</span>
              </template>
              <div style="padding:10px 0">
                <p style="color:#8fa7b8;font-size:13px;margin-bottom:14px">一键强制解锁船长室/船内军械库铁门，无需寻找密码钥匙。</p>
                <el-button type="warning" :icon="Unlock" :loading="isSubmitting" @click="submitAction('open_armory', {})">开启军械库</el-button>
              </div>
            </el-tab-pane>

            <el-tab-pane name="kick">
              <template #label>
                <span><el-icon style="vertical-align:middle;margin-right:2px"><RemoveFilled /></el-icon> 踢出玩家</span>
              </template>
              <el-form label-position="top" size="small">
                <el-form-item label="选择目标玩家">
                  <el-select v-model="formKick.player" placeholder="选择要踢出的玩家" style="width:100%">
                    <el-option v-for="p in playerList" :key="p.index" :label="p.name + (p.role ? ' ' + p.role : '') + ' #' + p.index" :value="p.name" />
                  </el-select>
                </el-form-item>
                <el-form-item label="踢出原因 (可选)">
                  <el-input v-model="formKick.reason" placeholder="例如：挂机、消极游戏或言语不当" />
                </el-form-item>
                <el-button type="danger" :icon="Delete" :loading="isSubmitting" @click="submitAction('kick_player', formKick)">确认踢出</el-button>
              </el-form>
            </el-tab-pane>

            <el-tab-pane name="revive">
              <template #label>
                <span><el-icon style="vertical-align:middle;margin-right:2px"><FirstAidKit /></el-icon> 复活玩家</span>
              </template>
              <el-form label-position="top" size="small">
                <el-form-item label="选择需要复活的玩家">
                  <el-select v-model="formRevive.player" placeholder="选择目标玩家" style="width:100%">
                    <el-option v-for="p in playerList" :key="p.index" :label="p.name + (p.role ? ' ' + p.role : '') + ' #' + p.index" :value="p.name" />
                  </el-select>
                </el-form-item>
                <el-button type="success" :icon="CircleCheckFilled" :loading="isSubmitting" @click="submitAction('revive_player', formRevive)">立即复活玩家</el-button>
              </el-form>
            </el-tab-pane>

            <el-tab-pane name="teleport">
              <template #label>
                <span><el-icon style="vertical-align:middle;margin-right:2px"><LocationFilled /></el-icon> 坐标传送</span>
              </template>
              <el-form label-position="top" size="small">
                <el-form-item label="传送目标玩家">
                  <el-select v-model="formTeleport.player" placeholder="选择目标玩家" style="width:100%">
                    <el-option label="🚢 全部玩家 (全员召回船只)" value="all" />
                    <el-option v-for="p in playerList" :key="p.index" :label="p.name + (p.role ? ' ' + p.role : '') + ' #' + p.index" :value="p.name" />
                  </el-select>
                </el-form-item>
                <el-button type="primary" :icon="Position" :loading="isSubmitting" @click="submitAction('teleport_to_ship', formTeleport)">执行传送</el-button>

                <el-divider content-position="left">传送至世界坐标（厘米）</el-divider>
                <el-form-item label="预设点位">
                  <div style="display:flex;gap:8px;width:100%">
                    <el-select v-model="formCoordinate.preset" clearable placeholder="选择已保存点位" style="flex:1" @change="applyTeleportPreset">
                      <el-option v-for="preset in teleportPresets" :key="preset.name" :label="preset.name + ' · ' + formatCoord(preset.x) + ', ' + formatCoord(preset.y) + ', ' + formatCoord(preset.z)" :value="preset.name" />
                    </el-select>
                    <el-button type="danger" plain :disabled="!formCoordinate.preset" @click="removeTeleportPreset">删除</el-button>
                  </div>
                </el-form-item>
                <el-form-item label="选择目标玩家">
                  <el-select v-model="formCoordinate.player" placeholder="选择在线玩家" style="width:100%" @change="fillCurrentCoordinates">
                    <el-option v-for="p in playerList" :key="p.index" :label="p.name + (p.role ? ' · ' + p.role : '') + ' #' + p.index" :value="p.name" :disabled="!p.has_pawn || p.is_dead" />
                  </el-select>
                </el-form-item>
                <el-row :gutter="10">
                  <el-col :span="8"><el-form-item label="X"><el-input-number v-model="formCoordinate.x" :controls="false" style="width:100%" /></el-form-item></el-col>
                  <el-col :span="8"><el-form-item label="Y"><el-input-number v-model="formCoordinate.y" :controls="false" style="width:100%" /></el-form-item></el-col>
                  <el-col :span="8"><el-form-item label="Z"><el-input-number v-model="formCoordinate.z" :controls="false" style="width:100%" /></el-form-item></el-col>
                </el-row>
                <el-form-item label="保存当前 XYZ 为预设">
                  <div style="display:flex;gap:8px;width:100%">
                    <el-input v-model="formCoordinate.presetName" maxlength="40" placeholder="例如：船长室、锅炉房、码头" />
                    <el-button type="success" plain @click="saveTeleportPreset">保存点位</el-button>
                  </div>
                </el-form-item>
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                  <el-button :icon="Refresh" @click="fillCurrentCoordinates">填入当前位置</el-button>
                  <el-button type="warning" :icon="Position" :loading="isSubmitting" @click="submitAction('teleport_player', formCoordinate)">传送至 XYZ</el-button>
                </div>
              </el-form>
            </el-tab-pane>

            <el-tab-pane name="items">
              <template #label>
                <span><el-icon style="vertical-align:middle;margin-right:2px"><Box /></el-icon> 发送物品</span>
              </template>
              <el-alert title="特殊物品可能依赖 Mod PAK，未装载时会安全返回错误。" type="warning" :closable="false" style="margin-bottom:14px" />
              <el-form label-position="top" size="small">
                <el-form-item label="选择目标职业">
                  <el-select v-model="formItem.role" placeholder="选择在线职业" style="width:100%">
                    <el-option label="📦 全部在线玩家（每人发放）" value="all" />
                    <el-option v-for="p in rolePlayerOptions" :key="p.role_id" :label="p.role + ' · ' + p.name" :value="p.role_id" :disabled="!p.has_pawn || p.is_dead" />
                  </el-select>
                </el-form-item>
                <el-form-item label="选择物品">
                  <el-select v-model="formItem.item" filterable placeholder="搜索或选择物品" style="width:100%">
                    <el-option-group v-for="(items, category) in itemGroups" :key="category" :label="category">
                      <el-option v-for="item in items" :key="item.id" :value="item.id" :label="item.name + (item.special ? ' ⚠' : '')">
                        <span>{{ item.name }}</span>
                        <span v-if="item.requires_mod" style="float:right;color:#e6a23c">需要 Mod</span>
                        <span v-else-if="item.special" style="float:right;color:#e6a23c">特殊</span>
                      </el-option>
                    </el-option-group>
                  </el-select>
                </el-form-item>
                <el-form-item label="数量（单次 1–20）">
                  <el-input-number v-model="formItem.quantity" :min="1" :max="20" :step="1" />
                </el-form-item>
                <el-button type="success" :icon="Promotion" :loading="isSubmitting" @click="submitAction('give_item', formItem)">立即发送物品</el-button>
              </el-form>
            </el-tab-pane>

            <el-tab-pane name="card-reward">
              <template #label>
                <span><el-icon style="vertical-align:middle;margin-right:2px"><Trophy /></el-icon> 赢牌奖励</span>
              </template>
              <el-alert title="配置保存后从下一局生效，无需重启注入器。实际赢牌玩家由摊牌结果自动识别。" type="success" :closable="false" style="margin-bottom:14px" />
              <el-form label-position="top" size="small">
                <el-form-item label="启用奖励">
                  <el-switch v-model="rewardConfig.enabled" active-text="启用" inactive-text="停用" />
                </el-form-item>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px">
                  <el-form-item label="奖励模式">
                    <el-radio-group v-model="rewardConfig.mode" size="small" style="display:flex;flex-wrap:wrap;row-gap:6px">
                      <el-radio-button label="fixed">固定奖励（全部发放）</el-radio-button>
                      <el-radio-button label="random">随机奖励（随机一种）</el-radio-button>
                    </el-radio-group>
                  </el-form-item>
                  <el-form-item label="开局后发放（秒）">
                    <el-input-number v-model="rewardConfig.delay_seconds" :min="0" :max="600" :step="1" style="width:100%" />
                  </el-form-item>
                  <el-form-item label="奖励后背包总格数（0=不调整）">
                    <el-input-number v-model="rewardConfig.backpack_slots" :min="0" :max="30" :step="1" style="width:100%" />
                  </el-form-item>
                </div>
                <el-form-item label="奖励物品（最多 8 种，每种 1–20 个）">
                  <div style="width:100%;display:flex;flex-direction:column;gap:8px">
                    <div v-for="(reward, index) in rewardConfig.items" :key="index" style="display:grid;grid-template-columns:minmax(0,1fr) 120px 78px;gap:8px;align-items:center">
                      <el-select v-model="reward.item" filterable placeholder="选择物品" style="width:100%">
                        <el-option-group v-for="(items, category) in itemGroups" :key="category" :label="category">
                          <el-option v-for="item in items" :key="item.id" :value="item.id" :label="item.name + (item.special ? ' ⚠' : '')" />
                        </el-option-group>
                      </el-select>
                      <el-input-number v-model="reward.quantity" :min="1" :max="20" :step="1" style="width:120px" />
                      <el-button type="danger" plain :icon="Delete" style="width:100%" @click="removeRewardItem(index)">删除</el-button>
                    </div>
                    <el-button v-if="rewardConfig.items.length < 8" plain :icon="Box" @click="addRewardItem">添加奖励物品</el-button>
                  </div>
                </el-form-item>
                <el-form-item label="全服公告（{player}=赢牌职业，{rewards}=奖励内容）">
                  <el-input v-model="rewardConfig.announcement" type="textarea" :rows="3" maxlength="500" show-word-limit />
                </el-form-item>
                <el-button type="success" :icon="Check" :loading="rewardSaving" @click="saveWinningCardReward">保存赢牌奖励配置</el-button>
              </el-form>
            </el-tab-pane>

            <el-tab-pane name="execute">
              <template #label>
                <span style="color:#f56c6c"><el-icon style="vertical-align:middle;margin-right:2px"><WarningFilled /></el-icon> 处决玩家</span>
              </template>
              <el-alert title="目标角色会立即死亡，并在死亡同步 1 秒后被踢出服务器。" type="error" :closable="false" style="margin-bottom:14px" />
              <el-form label-position="top" size="small">
                <el-form-item label="选择目标职业">
                  <el-select v-model="formExecute.role" placeholder="选择要处决的在线职业" style="width:100%">
                    <el-option v-for="p in rolePlayerOptions" :key="p.role_id" :label="p.role + ' · ' + p.name" :value="p.role_id" :disabled="!p.has_pawn || p.is_dead" />
                  </el-select>
                </el-form-item>
                <el-button type="danger" :icon="DeleteFilled" :loading="isSubmitting" @click="confirmExecute">确认处决并踢出</el-button>
              </el-form>
            </el-tab-pane>

            <el-tab-pane name="blacklist">
              <template #label>
                <span><el-icon style="vertical-align:middle;margin-right:2px"><RemoveFilled /></el-icon> 黑名单</span>
              </template>
              <el-alert title="进服器只读查询令牌" type="info" :closable="false" style="margin-bottom:14px">
                <template #default>
                  <div style="display:flex;gap:8px;align-items:center;margin-top:6px">
                    <el-input v-model="blacklistCheckToken" readonly />
                    <el-button :icon="DocumentCopy" @click="copyBlacklistToken">复制令牌</el-button>
                  </div>
                  <div style="margin-top:6px;color:#8fa7b8">该令牌只能检查大厅黑名单，不能执行任何 GM 管理操作。</div>
                </template>
              </el-alert>
              <el-form label-position="top" size="small">
                <el-form-item label="选择在线玩家（自动读取 Steam / EOS ID）">
                  <el-select v-model="formBlacklist.player" placeholder="选择要拉黑的玩家" style="width:100%">
                    <el-option
                      v-for="p in playerList"
                      :key="p.index"
                      :label="p.name + (p.steam_id ? ' · Steam ' + p.steam_id : ' · ID 读取中')"
                      :value="p.name"
                      :disabled="!p.user_id"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="预设理由">
                  <el-select v-model="formBlacklist.reason_code" style="width:100%">
                    <el-option v-for="(label, code) in blacklistPresets" :key="code" :label="label" :value="code" />
                  </el-select>
                </el-form-item>
                <el-form-item label="自定义理由（填写后覆盖预设文字）">
                  <el-input v-model="formBlacklist.reason" maxlength="200" show-word-limit placeholder="例如：多次死亡后立即退出，已有录像" />
                </el-form-item>
                <el-button type="danger" :icon="RemoveFilled" :loading="isSubmitting" @click="addBlacklist">一键拉黑选中玩家</el-button>
              </el-form>

              <el-divider content-position="left">历史记录管理</el-divider>
              <div style="border:1px solid #20364d;background:#0b1521;border-radius:8px;padding:18px;display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap">
                <div>
                  <div style="font-weight:700;font-size:15px;margin-bottom:5px">当前共 {{ blacklistList.length }} 条黑名单记录</div>
                  <div style="color:#8fa7b8;font-size:12.5px">搜索、筛选、编辑理由、复制身份信息与导出操作已移至独立页面。</div>
                </div>
                <el-button type="primary" :icon="List" @click="openBlacklistCenter">打开黑名单管理中心</el-button>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <el-card shadow="hover">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <div style="display:flex;align-items:center;gap:6px;font-weight:600">
                <el-icon color="#409EFF"><Monitor /></el-icon>
                <span>GM 指令响应输出</span>
              </div>
              <div>
                <el-button size="small" :icon="DocumentCopy" @click="copyConsoleLog">复制</el-button>
                <el-button size="small" :icon="Delete" @click="consoleOutput = '(暂无指令执行记录)'">清空</el-button>
              </div>
            </div>
          </template>
          <div class="result-console" ref="consoleRef">{{ consoleOutput }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</div>

<script>
const { createApp, ref, reactive, computed, onMounted, nextTick } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;
const {
  Compass, User, UserFilled, Refresh, SwitchButton, InfoFilled, Tickets, Operation,
  ChatDotRound, Promotion, Trophy, CircleCloseFilled, Key, Unlock, RemoveFilled, Delete,
  FirstAidKit, CircleCheckFilled, LocationFilled, Position, Monitor, DocumentCopy, Check, List,
  View, Box, WarningFilled, DeleteFilled
} = ElementPlusIconsVue;

const app = createApp({
  setup() {
    const isLoggedIn = ref(localStorage.getItem('gm_token') !== null);
    const loginPwd = ref('');
    const isLoggingIn = ref(false);
    const isRefreshing = ref(false);
    const isSubmitting = ref(false);
    const rewardSaving = ref(false);

    const activeTab = ref('thralls');
    const playerState = reactive({ count: 0, stale: false, timestamp: null });
    const playerList = ref([]);
    const playerFilter = ref('all');
    const thrallList = computed(() => playerList.value.filter(p => p.is_thrall === true));
    const explorerList = computed(() => playerList.value.filter(p => !p.is_thrall));
    const filteredPlayerList = computed(() => {
      if (playerFilter.value === 'thralls') return thrallList.value;
      if (playerFilter.value === 'explorers') return explorerList.value;
      return playerList.value;
    });
    const rolePlayerOptions = computed(() => playerList.value.filter(p => p.role_id));

    const blacklistList = ref([]);
    const blacklistPresets = ref({});
    const blacklistCheckToken = ref('');
    const teleportPresets = ref([]);
    const itemCatalog = ref([]);
    const itemGroups = computed(() => itemCatalog.value.reduce((groups, entry) => {
      (groups[entry.category] ||= []).push(entry);
      return groups;
    }, {}));
    const consoleOutput = ref('(等待指令执行...)');
    const consoleRef = ref(null);

    const formMsg = reactive({ player: 'all', message: '' });
    const formEnd = reactive({ team: 1 });
    const formKick = reactive({ player: '', reason: '' });
    const formRevive = reactive({ player: '' });
    const formTeleport = reactive({ player: 'all' });
    const formCoordinate = reactive({ player: '', preset: '', presetName: '', x: 0, y: 0, z: 0 });
    const formItem = reactive({ role: '', item: '', quantity: 1 });
    const rewardConfig = reactive({
      enabled: false, mode: 'fixed', delay_seconds: 30, backpack_slots: 0,
      items: [{ item: 'coal', quantity: 5 }],
      announcement: '[牌局奖励] {player} 获得开局奖励：{rewards}'
    });
    const formExecute = reactive({ role: '' });
    const formBlacklist = reactive({ player: '', reason_code: 'quit_after_death', reason: '' });

    async function api(url, options = {}) {
      options.headers = options.headers || {};
      const token = localStorage.getItem('gm_token');
      if (token) {
        options.headers['Authorization'] = 'Bearer ' + token;
      }
      const res = await fetch(url, options);
      if (res.status === 401) {
        localStorage.removeItem('gm_token');
        isLoggedIn.value = false;
        throw new Error('未认证，请先登录');
      }
      let d = {};
      try { d = await res.json(); } catch(e) {}
      if (!res.ok || d.error) throw new Error(d.error || ('HTTP ' + res.status));
      return d;
    }

    async function doLogin() {
      if (!loginPwd.value) {
        ElMessage.warning('请输入密码');
        return;
      }
      isLoggingIn.value = true;
      try {
        const res = await fetch('/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: loginPwd.value })
        });
        const d = await res.json();
        if (res.ok && d.ok) {
          if (d.token) {
            localStorage.setItem('gm_token', d.token);
          }
          isLoggedIn.value = true;
          loginPwd.value = '';
          ElMessage.success('登录成功');
          await fetchPlayers();
          await Promise.all([fetchBlacklist(), fetchItems(), fetchTeleportPresets(), fetchWinningCardReward()]);
        } else {
          ElMessage.error(d.error || '密码错误');
        }
      } catch(e) {
        ElMessage.error(e.message);
      } finally {
        isLoggingIn.value = false;
      }
    }

    async function doLogout() {
      localStorage.removeItem('gm_token');
      isLoggedIn.value = false;
      try {
        await fetch('/logout');
      } catch(e) {}
      ElMessage.info('已退出登录');
    }

    async function fetchPlayers() {
      isRefreshing.value = true;
      try {
        const data = await api('/api/gm/players');
        isLoggedIn.value = true;
        playerState.count = data.count || 0;
        playerState.stale = data.stale === true;
        playerState.timestamp = data.timestamp;
        playerList.value = data.players || [];
      } catch(e) {
        // Handled in api()
      } finally {
        isRefreshing.value = false;
      }
    }

    async function fetchBlacklist() {
      try {
        const data = await api('/api/gm/blacklist');
        blacklistList.value = data.entries || [];
        blacklistPresets.value = data.reason_presets || {};
        blacklistCheckToken.value = data.check_token || '';
      } catch(e) {
        // Handled in api()
      }
    }

    async function fetchItems() {
      try {
        const data = await api('/api/gm/items');
        itemCatalog.value = data.items || [];
      } catch(e) {
        // Handled in api()
      }
    }

    async function fetchTeleportPresets() {
      try {
        const data = await api('/api/gm/teleport_presets');
        teleportPresets.value = data.presets || [];
      } catch(e) {
        // Handled in api()
      }
    }

    async function fetchWinningCardReward() {
      try {
        const data = await api('/api/gm/winning-card-reward');
        const config = data.config || {};
        rewardConfig.enabled = config.enabled === true;
        rewardConfig.mode = config.mode || 'fixed';
        rewardConfig.delay_seconds = Number(config.delay_seconds ?? 30);
        rewardConfig.backpack_slots = Number(config.backpack_slots ?? 0);
        rewardConfig.items = Array.isArray(config.items)
          ? config.items.map(entry => ({ item: entry.item, quantity: Number(entry.quantity || 1) }))
          : [];
        rewardConfig.announcement = config.announcement || '';
      } catch(e) {
        // Handled in api()
      }
    }

    function addRewardItem() {
      if (rewardConfig.items.length < 8) rewardConfig.items.push({ item: '', quantity: 1 });
    }

    function removeRewardItem(index) {
      rewardConfig.items.splice(index, 1);
    }

    async function saveWinningCardReward() {
      rewardSaving.value = true;
      try {
        const payload = {
          enabled: rewardConfig.enabled === true,
          mode: rewardConfig.mode,
          delay_seconds: Number(rewardConfig.delay_seconds),
          backpack_slots: Number(rewardConfig.backpack_slots),
          items: rewardConfig.items.map(entry => ({ item: entry.item, quantity: Number(entry.quantity) })),
          announcement: rewardConfig.announcement
        };
        await api('/api/gm/winning-card-reward', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        await fetchWinningCardReward();
        ElMessage.success('赢牌奖励配置已保存，将从下一局生效');
      } catch(e) {
        ElMessage.error('保存赢牌奖励失败: ' + e.message);
      } finally {
        rewardSaving.value = false;
      }
    }

    function formatCoord(value) {
      const number = Number(value);
      return Number.isFinite(number) ? number.toFixed(2) : '—';
    }

    function fillCurrentCoordinates() {
      const player = playerList.value.find(p => p.name === formCoordinate.player);
      if (!player || !player.has_pawn) {
        if (formCoordinate.player) ElMessage.warning('当前玩家没有可用坐标');
        return;
      }
      formCoordinate.x = Number(player.x);
      formCoordinate.y = Number(player.y);
      formCoordinate.z = Number(player.z);
      formCoordinate.preset = '';
    }

    function applyTeleportPreset(name) {
      const preset = teleportPresets.value.find(entry => entry.name === name);
      if (!preset) return;
      formCoordinate.x = Number(preset.x);
      formCoordinate.y = Number(preset.y);
      formCoordinate.z = Number(preset.z);
      formCoordinate.presetName = preset.name;
    }

    async function saveTeleportPreset() {
      const name = formCoordinate.presetName.trim();
      const coordinates = [formCoordinate.x, formCoordinate.y, formCoordinate.z];
      if (!name) {
        ElMessage.warning('请填写预设名称');
        return;
      }
      if (coordinates.some(value => value === null || value === '' || !Number.isFinite(Number(value)))) {
        ElMessage.warning('请填写有效坐标');
        return;
      }
      try {
        const data = await api('/api/gm/teleport_presets/save', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, x: Number(coordinates[0]), y: Number(coordinates[1]), z: Number(coordinates[2]) })
        });
        await fetchTeleportPresets();
        formCoordinate.preset = data.preset.name;
        ElMessage.success('预设点位已保存');
      } catch(e) {
        ElMessage.error('保存预设失败: ' + e.message);
      }
    }

    async function removeTeleportPreset() {
      if (!formCoordinate.preset) return;
      try {
        await ElMessageBox.confirm(`确定删除预设点位【${formCoordinate.preset}】吗？`, '删除预设', {
          confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning'
        });
      } catch(e) { return; }
      try {
        await api('/api/gm/teleport_presets/remove', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: formCoordinate.preset })
        });
        formCoordinate.preset = '';
        formCoordinate.presetName = '';
        await fetchTeleportPresets();
        ElMessage.success('预设点位已删除');
      } catch(e) {
        ElMessage.error('删除预设失败: ' + e.message);
      }
    }

    function quickSelectPlayer(name) {
      const player = playerList.value.find(p => p.name === name);
      formMsg.player = name;
      formKick.player = name;
      formRevive.player = name;
      formTeleport.player = name;
      formBlacklist.player = name;
      formCoordinate.player = name;
      if (player && player.role_id) {
        formItem.role = player.role_id;
        formExecute.role = player.role_id;
        fillCurrentCoordinates();
      }
      ElMessage.info(`已选中玩家: ${name}`);
    }

    function quickTeleportPlayer(name) {
      ElMessageBox.confirm(`确定将玩家【${name}】传送回船吗？`, '传送确认', {
        confirmButtonText: '确认传送',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        submitAction('teleport_to_ship', { player: name });
      }).catch(() => {});
    }

    function quickRevivePlayer(name) {
      ElMessageBox.confirm(`确定复活玩家【${name}】吗？`, '复活确认', {
        confirmButtonText: '确认复活',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        submitAction('revive_player', { player: name });
      }).catch(() => {});
    }

    function quickKickPlayer(name) {
      ElMessageBox.prompt(`请输入踢出玩家【${name}】的原因（可选）：`, '踢出玩家', {
        confirmButtonText: '确认踢出',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：消极游戏 / 违规'
      }).then(({ value }) => {
        submitAction('kick_player', { player: name, reason: value || '' });
      }).catch(() => {});
    }

    function directEndGame(team) {
      const teamName = team === 1 ? '探险者 (好人胜利)' : '叛徒 (狼人胜利)';
      ElMessageBox.confirm(`确定要强制结算当前对局，并判定【${teamName}】获胜吗？`, '判胜确认', {
        confirmButtonText: '确定判定',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        submitAction('end_game', { team: team });
      }).catch(() => {});
    }

    async function addBlacklist() {
      if (!formBlacklist.player) {
        ElMessage.warning('请先选择在线玩家');
        return;
      }
      const player = playerList.value.find(p => p.name === formBlacklist.player);
      const identity = player && player.user_id ? `\n用户 ID：${player.user_id}` : '';
      try {
        await ElMessageBox.confirm(
          `确定拉黑【${formBlacklist.player}】吗？${identity}`,
          '加入黑名单',
          { confirmButtonText: '确认拉黑', cancelButtonText: '取消', type: 'warning' }
        );
      } catch(e) { return; }
      isSubmitting.value = true;
      try {
        const res = await api('/api/gm/blacklist/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formBlacklist)
        });
        ElMessage.success(`已拉黑 ${res.entry.name}`);
        formBlacklist.reason = '';
        await Promise.all([fetchPlayers(), fetchBlacklist()]);
      } catch(e) {
        ElMessage.error('拉黑失败: ' + e.message);
      } finally {
        isSubmitting.value = false;
      }
    }

    async function removeBlacklist(entry) {
      try {
        await ElMessageBox.confirm(`确定将【${entry.name}】移出黑名单吗？`, '移出黑名单', {
          confirmButtonText: '确认移除', cancelButtonText: '取消', type: 'warning'
        });
      } catch(e) { return; }
      try {
        await api('/api/gm/blacklist/remove', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: entry.user_id })
        });
        ElMessage.success('已移出黑名单');
        await Promise.all([fetchPlayers(), fetchBlacklist()]);
      } catch(e) {
        ElMessage.error('移除失败: ' + e.message);
      }
    }

    function copyBlacklistToken() {
      navigator.clipboard.writeText(blacklistCheckToken.value).then(() => {
        ElMessage.success('只读查询令牌已复制');
      }).catch(() => ElMessage.warning('复制失败，请手动复制'));
    }

    function openBlacklistCenter() {
      window.location.href = '/blacklist';
    }

    async function submitAction(action, params) {
      if (action === 'give_item') {
        if (!params.role || !params.item) {
          ElMessage.warning('请选择在线职业和物品');
          return;
        }
        if (!Number.isInteger(params.quantity) || params.quantity < 1 || params.quantity > 20) {
          ElMessage.warning('物品数量必须是 1 到 20 的整数');
          return;
        }
      }
      if (action === 'teleport_player') {
        const rawCoordinates = [params.x, params.y, params.z];
        const coordinates = rawCoordinates.map(Number);
        if (!params.player || rawCoordinates.some(value => value === null || value === '' || typeof value === 'boolean') || coordinates.some(value => !Number.isFinite(value) || Math.abs(value) > 10000000)) {
          ElMessage.warning('请选择在线玩家并填写安全范围内的有效坐标');
          return;
        }
        params = { player: params.player, x: coordinates[0], y: coordinates[1], z: coordinates[2] };
      }
      isSubmitting.value = true;
      try {
        const res = await api('/api/gm/' + action, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params)
        });
        const state = res.queued ? '已进入队列，3 秒内尚未返回原生结果' : (res.message || '执行成功');
        const resultLine = res.result ? `\n结果: ${JSON.stringify(res.result)}` : '';
        const logLine = `[${new Date().toLocaleTimeString()}] ${res.queued ? '…' : '✓'} 指令【${action}】${state} (ID: ${res.command_id})\n参数: ${JSON.stringify(params)}${resultLine}`;
        consoleOutput.value = logLine + '\n\n' + consoleOutput.value;
        if (res.queued) ElMessage.warning('指令已排队，原生执行结果尚未返回');
        else ElMessage.success(state);
        if (action === 'send_message') formMsg.message = '';
        if (['revive_player', 'teleport_to_ship', 'teleport_player', 'execute_player', 'skip_poker'].includes(action)) {
          setTimeout(fetchPlayers, action === 'execute_player' ? 1200 : 200);
        }
      } catch(e) {
        const logLine = `[${new Date().toLocaleTimeString()}] ✗ 指令【${action}】执行失败: ${e.message}`;
        consoleOutput.value = logLine + '\n\n' + consoleOutput.value;
        ElMessage.error('操作失败: ' + e.message);
      } finally {
        isSubmitting.value = false;
      }
    }

    function confirmEndGame() {
      const teamName = formEnd.team === 1 ? '探险者 (Explorers)' : '叛徒 (Thralls)';
      ElMessageBox.confirm(`确定要强制结束当前对局，并判定【${teamName}】获胜吗？`, '危险操作确认', {
        confirmButtonText: '确定结束',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        submitAction('end_game', { team: parseInt(formEnd.team) });
      }).catch(() => {});
    }

    function confirmSkipPoker() {
      ElMessageBox.confirm(
        '确定跳过当前打牌阶段吗？服务端会立即结束牌局、随机分配狼人并开始正式游戏。',
        '跳过打牌确认',
        { confirmButtonText: '确认跳过并开局', cancelButtonText: '取消', type: 'warning' }
      ).then(() => submitAction('skip_poker', {})).catch(() => {});
    }

    function confirmExecute() {
      if (!formExecute.role) {
        ElMessage.warning('请选择要处决的在线职业');
        return;
      }
      const player = playerList.value.find(p => p.role_id === formExecute.role);
      const target = player ? `${player.role} · ${player.name}` : formExecute.role;
      ElMessageBox.confirm(
        `确定处决【${target}】吗？角色会立即死亡，验证成功后约 1 秒被踢出服务器。`,
        '危险操作确认',
        { confirmButtonText: '确认处决', cancelButtonText: '取消', type: 'error' }
      ).then(() => submitAction('execute_player', { role: formExecute.role })).catch(() => {});
    }

    function copyConsoleLog() {
      navigator.clipboard.writeText(consoleOutput.value).then(() => {
        ElMessage.success('控制台日志已复制');
      }).catch(() => {
        ElMessage.warning('复制失败，请手动选取');
      });
    }

    onMounted(async () => {
      await fetchPlayers();
      if (isLoggedIn.value) await Promise.all([fetchBlacklist(), fetchItems(), fetchTeleportPresets(), fetchWinningCardReward()]);
      setInterval(() => {
        if (isLoggedIn.value) {
          fetchPlayers();
        }
      }, 1000);
    });

    return {
      isLoggedIn, loginPwd, isLoggingIn, isRefreshing, isSubmitting, rewardSaving,
      activeTab, playerState, playerList, playerFilter, thrallList, explorerList, filteredPlayerList,
      rolePlayerOptions, blacklistList, blacklistPresets, blacklistCheckToken, teleportPresets, itemCatalog, itemGroups, consoleOutput, consoleRef,
      formMsg, formEnd, formKick, formRevive, formTeleport, formCoordinate, formItem, rewardConfig, formExecute, formBlacklist,
      Compass, User, UserFilled, Refresh, SwitchButton, InfoFilled, Tickets, Operation,
      ChatDotRound, Promotion, Trophy, CircleCloseFilled, Key, Unlock, RemoveFilled, Delete,
      FirstAidKit, CircleCheckFilled, LocationFilled, Position, Monitor, DocumentCopy, Check, List, View,
      Box, WarningFilled, DeleteFilled,
      doLogin, doLogout, fetchPlayers, fetchBlacklist, fetchItems, fetchTeleportPresets, fetchWinningCardReward, formatCoord, fillCurrentCoordinates,
      applyTeleportPreset, saveTeleportPreset, removeTeleportPreset,
      addRewardItem, removeRewardItem, saveWinningCardReward,
      quickSelectPlayer, quickTeleportPlayer, quickRevivePlayer, quickKickPlayer, directEndGame, submitAction,
      addBlacklist, removeBlacklist, copyBlacklistToken, openBlacklistCenter, confirmEndGame, confirmSkipPoker, confirmExecute, copyConsoleLog
    };
  }
});
app.use(ElementPlus, { locale: ElementPlusLocaleZhCn });
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}
app.mount('#app');
</script>
</body>
</html>'''


def blacklist_html() -> str:
    return r'''<!doctype html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>黑名单管理中心 · Dread Hunger</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/element-plus@2.8.0/dist/index.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/element-plus@2.8.0/theme-chalk/dark/css-vars.css">
  <script src="https://cdn.jsdelivr.net/npm/vue@3.4.38/dist/vue.global.prod.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/element-plus@2.8.0/dist/index.full.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/@element-plus/icons-vue@2.3.1/dist/index.iife.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/element-plus@2.8.0/dist/locale/zh-cn.min.js"></script>
  <style>
    :root {
      --ink:#071019; --panel:#0d1926; --panel-2:#111f2e; --line:#20364c;
      --text:#e8f0f7; --muted:#8299ac; --ice:#44a5ff; --red:#ff5d62;
      --amber:#dca84c; --green:#63cf8b;
    }
    * { box-sizing:border-box; }
    [v-cloak] { display:none; }
    html,body,#app { min-height:100%; }
    body {
      margin:0; color:var(--text); background:
        radial-gradient(circle at 78% -10%,rgba(47,116,173,.20),transparent 36%),
        linear-gradient(rgba(255,255,255,.014) 1px,transparent 1px),
        linear-gradient(90deg,rgba(255,255,255,.014) 1px,transparent 1px),var(--ink);
      background-size:auto,32px 32px,32px 32px,auto;
      font-family:"HarmonyOS Sans SC","Microsoft YaHei UI","Noto Sans SC",sans-serif;
    }
    body:before {
      content:"";position:fixed;inset:0;pointer-events:none;opacity:.18;
      background:linear-gradient(115deg,transparent 0 48%,rgba(68,165,255,.08) 48.2%,transparent 48.5%);
    }
    .shell { max-width:1640px;margin:0 auto;padding:22px 26px 42px;position:relative; }
    .masthead {
      min-height:92px;display:flex;align-items:center;justify-content:space-between;gap:24px;
      padding:18px 22px;border:1px solid var(--line);border-radius:12px;
      background:linear-gradient(100deg,rgba(18,35,52,.98),rgba(9,19,30,.96));
      box-shadow:0 18px 60px rgba(0,0,0,.28);position:relative;overflow:hidden;
    }
    .masthead:after { content:"CREW DISCIPLINE LEDGER";position:absolute;right:22px;bottom:-12px;color:rgba(255,255,255,.028);font-size:42px;font-weight:900;letter-spacing:4px; }
    .identity { display:flex;align-items:center;gap:15px;position:relative;z-index:1; }
    .seal { width:50px;height:50px;border:1px solid #32658e;border-radius:50%;display:grid;place-items:center;color:var(--ice);background:#0a1723;box-shadow:inset 0 0 18px rgba(68,165,255,.13); }
    .eyebrow { color:var(--ice);font-size:10px;font-weight:800;letter-spacing:2.4px;text-transform:uppercase;margin-bottom:4px; }
    h1 { margin:0;font-size:24px;letter-spacing:.5px;font-weight:800; }
    .subtitle { margin-top:4px;color:var(--muted);font-size:12.5px; }
    .mast-actions { display:flex;gap:9px;align-items:center;position:relative;z-index:1;flex-wrap:wrap;justify-content:flex-end; }
    .stat-grid { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0; }
    .stat-card { min-height:102px;padding:16px 18px;border:1px solid var(--line);border-radius:10px;background:linear-gradient(145deg,rgba(17,31,46,.98),rgba(10,20,31,.98));position:relative;overflow:hidden; }
    .stat-card:after { content:"";position:absolute;width:58px;height:58px;border:1px solid currentColor;border-radius:50%;right:-20px;top:-20px;opacity:.11; }
    .stat-label { color:var(--muted);font-size:11px;letter-spacing:1px;margin-bottom:8px; }
    .stat-value { font-family:"Cascadia Code","JetBrains Mono",monospace;font-size:28px;font-weight:800;line-height:1; }
    .stat-note { margin-top:8px;color:#6f879a;font-size:11px; }
    .blue { color:var(--ice); }.red { color:var(--red); }.amber { color:var(--amber); }.green { color:var(--green); }
    .token-strip { display:grid;grid-template-columns:auto minmax(260px,1fr) auto;align-items:center;gap:13px;padding:12px 15px;margin-bottom:12px;border:1px solid #24435e;border-radius:9px;background:rgba(16,35,51,.82); }
    .token-label { display:flex;gap:9px;align-items:center;white-space:nowrap;font-size:12px;font-weight:700;color:#aac5d9; }
    .workspace { border:1px solid var(--line);border-radius:12px;background:rgba(10,20,31,.97);overflow:hidden;box-shadow:0 22px 60px rgba(0,0,0,.24); }
    .workspace-head { padding:17px 18px 14px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,#111f2e,#0c1824); }
    .section-title { display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:13px; }
    .section-title h2 { margin:0;font-size:16px;letter-spacing:.3px; }
    .section-title small { color:var(--muted);font-weight:400;margin-left:9px; }
    .filters { display:grid;grid-template-columns:minmax(280px,1.5fr) minmax(170px,.6fr) minmax(150px,.5fr) auto;gap:10px; }
    .table-wrap { padding:0 14px 12px; }
    .player-cell { display:flex;align-items:center;gap:10px;min-width:0; }
    .avatar-mark { width:34px;height:34px;flex:0 0 auto;border-radius:7px;border:1px solid #31506b;background:#0a1722;color:#78bfff;display:grid;place-items:center;font-weight:800; }
    .player-name { font-weight:750;color:#edf5fb;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
    .alias-line { font-size:10.5px;color:#70879a;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px; }
    .mono { font-family:"Cascadia Code","JetBrains Mono",monospace;font-size:11.5px;color:#b7c9d7; }
    .id-cell { display:flex;align-items:center;gap:5px; }
    .reason-cell { line-height:1.45; }
    .reason-text { margin-top:5px;color:#c8d5df;font-size:12px; }
    .time-cell { color:#8ba0b1;font-size:11.5px;line-height:1.55; }
    .pager { display:flex;align-items:center;justify-content:space-between;padding:13px 5px 2px;color:var(--muted);font-size:12px; }
    .empty-state { padding:62px 20px;text-align:center;color:var(--muted); }
    .detail-grid { display:grid;grid-template-columns:110px 1fr;gap:12px 15px;font-size:13px; }
    .detail-grid dt { color:var(--muted); }.detail-grid dd { margin:0;word-break:break-all;color:#dce8f0; }
    .drawer-hero { padding:16px;border:1px solid var(--line);border-radius:9px;background:#0b1723;margin-bottom:18px; }
    .drawer-name { font-size:20px;font-weight:800;margin-bottom:7px; }
    .el-table { --el-table-bg-color:transparent!important;--el-table-tr-bg-color:transparent!important;--el-table-header-bg-color:#0c1824!important;--el-table-border-color:#1c3043!important;--el-table-row-hover-bg-color:#11263a!important;color:#dbe6ee!important; }
    .el-table th.el-table__cell { color:#829bae!important;font-size:11px;letter-spacing:.7px;text-transform:uppercase;height:44px; }
    .el-table td.el-table__cell { padding:11px 0!important; }
    .el-dialog,.el-drawer { background:#0e1a27!important;border:1px solid var(--line); }
    .el-input__wrapper,.el-select__wrapper,.el-textarea__inner { background:#08131e!important;box-shadow:0 0 0 1px #23394c inset!important; }
    .el-pagination { --el-pagination-bg-color:#101e2c;--el-pagination-button-disabled-bg-color:#0c1722; }
    @media (max-width:980px) { .stat-grid{grid-template-columns:repeat(2,1fr)}.filters{grid-template-columns:1fr 1fr}.filters .search{grid-column:1/-1}.masthead{align-items:flex-start}.masthead:after{display:none} }
    @media (max-width:640px) { .shell{padding:12px}.masthead{display:block}.mast-actions{margin-top:15px;justify-content:flex-start}.stat-grid{grid-template-columns:1fr 1fr}.token-strip{grid-template-columns:1fr}.filters{grid-template-columns:1fr}.filters .search{grid-column:auto}.stat-card{min-height:90px}.stat-value{font-size:23px} }
  </style>
</head>
<body class="dark">
<div id="blacklist-app" v-cloak>
  <main class="shell">
    <header class="masthead">
      <div class="identity">
        <div class="seal"><el-icon :size="25"><WarningFilled /></el-icon></div>
        <div>
          <div class="eyebrow">Crew discipline ledger · v''' + VERSION + r'''</div>
          <h1>黑名单管理中心</h1>
          <div class="subtitle">独立记录所有违规玩家，按身份识别，不受玩家改名影响</div>
        </div>
      </div>
      <div class="mast-actions">
        <el-button :icon="Back" @click="goBack">返回 GM 控制台</el-button>
        <el-button :icon="Download" @click="exportJson" :disabled="!filteredEntries.length">导出当前结果</el-button>
        <el-button type="danger" :icon="Plus" @click="openManualAdd">手动添加黑名单</el-button>
        <el-button type="primary" :icon="Refresh" :loading="loading" @click="fetchBlacklist">刷新档案</el-button>
      </div>
    </header>

    <section class="stat-grid">
      <article class="stat-card blue"><div class="stat-label">全部档案 / TOTAL</div><div class="stat-value">{{ entries.length }}</div><div class="stat-note">以 Steam / EOS 身份去重</div></article>
      <article class="stat-card red"><div class="stat-label">外挂与卡 BUG / CHEAT</div><div class="stat-value">{{ cheatCount }}</div><div class="stat-note">外挂和恶意利用漏洞</div></article>
      <article class="stat-card amber"><div class="stat-label">消极行为 / DISRUPTION</div><div class="stat-value">{{ disruptionCount }}</div><div class="stat-note">死退、摆烂及骚扰记录</div></article>
      <article class="stat-card green"><div class="stat-label">近 7 天更新 / RECENT</div><div class="stat-value">{{ recentCount }}</div><div class="stat-note">新建或修改过的档案</div></article>
    </section>

    <section class="token-strip">
      <div class="token-label"><el-icon color="#44a5ff"><Key /></el-icon>进服器只读查询令牌</div>
      <el-input v-model="checkToken" type="password" show-password readonly />
      <el-button :icon="DocumentCopy" @click="copyText(checkToken,'只读令牌')">复制令牌</el-button>
    </section>

    <section class="workspace">
      <div class="workspace-head">
        <div class="section-title">
          <h2>违规玩家档案 <small>筛选后 {{ filteredEntries.length }} 条</small></h2>
          <el-tag v-if="updatedAt" type="info" effect="plain">云端更新 {{ updatedAt }}</el-tag>
        </div>
        <div class="filters">
          <el-input class="search" v-model="keyword" clearable :prefix-icon="Search" placeholder="搜索玩家名、曾用名、Steam/EOS ID 或理由" />
          <el-select v-model="reasonFilter" placeholder="全部理由">
            <el-option label="全部理由" value="" />
            <el-option v-for="(label,code) in presets" :key="code" :label="label" :value="code" />
          </el-select>
          <el-select v-model="sortMode">
            <el-option label="最近更新" value="updated_desc" />
            <el-option label="最早加入" value="created_asc" />
            <el-option label="按玩家名" value="name_asc" />
          </el-select>
          <el-button :icon="Close" @click="clearFilters">清除筛选</el-button>
        </div>
      </div>

      <div class="table-wrap">
        <el-table v-if="filteredEntries.length" :data="pageEntries" row-key="user_id" style="width:100%">
          <el-table-column label="玩家档案" min-width="205" fixed="left">
            <template #default="scope">
              <div class="player-cell">
                <div class="avatar-mark">{{ firstChar(scope.row.name) }}</div>
                <div style="min-width:0"><div class="player-name">{{ scope.row.name || '未知玩家' }}</div><div class="alias-line" v-if="scope.row.aliases && scope.row.aliases.length">曾用：{{ scope.row.aliases.join(' / ') }}</div></div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="身份标识" min-width="225">
            <template #default="scope">
              <div class="id-cell"><span class="mono">Steam {{ scope.row.steam_id || '—' }}</span><el-button link :icon="DocumentCopy" @click="copyText(scope.row.steam_id,'Steam ID')" /></div>
              <div class="id-cell" style="margin-top:5px"><span class="mono">EOS {{ shortId(scope.row.eos_id) }}</span><el-button link :icon="DocumentCopy" @click="copyText(scope.row.eos_id,'EOS ID')" /></div>
            </template>
          </el-table-column>
          <el-table-column label="拉黑理由" min-width="250">
            <template #default="scope"><div class="reason-cell"><el-tag size="small" :type="reasonType(scope.row.reason_code)" effect="dark">{{ presets[scope.row.reason_code] || '其他' }}</el-tag><div class="reason-text">{{ scope.row.reason || '未填写' }}</div></div></template>
          </el-table-column>
          <el-table-column label="记录时间" min-width="168">
            <template #default="scope"><div class="time-cell">加入 {{ scope.row.created_at || '—' }}<br>更新 {{ scope.row.updated_at || '—' }}</div></template>
          </el-table-column>
          <el-table-column label="管理" width="180" fixed="right" align="right">
            <template #default="scope">
              <el-button link type="primary" @click="showDetail(scope.row)">详情</el-button>
              <el-button link type="warning" @click="openEdit(scope.row)">编辑</el-button>
              <el-button link type="danger" @click="removeEntry(scope.row)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="empty-state"><el-empty :description="entries.length ? '没有符合筛选条件的记录' : '黑名单暂无记录'" /></div>
        <div class="pager" v-if="filteredEntries.length">
          <span>第 {{ page }} 页，共 {{ filteredEntries.length }} 条</span>
          <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[15,30,50,100]" layout="sizes, prev, pager, next" :total="filteredEntries.length" background />
        </div>
      </div>
    </section>
  </main>

  <el-dialog v-model="addVisible" title="手动添加黑名单" width="600px" destroy-on-close>
    <el-form label-position="top">
      <el-form-item label="玩家名称（必填）"><el-input v-model="manualForm.player" maxlength="80" show-word-limit placeholder="填写游戏内玩家名" /></el-form-item>
      <el-form-item label="Steam ID"><el-input v-model="manualForm.steam_id" maxlength="17" placeholder="例如：76561198661845743" /></el-form-item>
      <el-form-item label="EOS ID 或完整用户 ID">
        <el-input v-model="manualForm.user_id" placeholder="32 位 EOS ID，或 SteamID_+_|EOSID" />
      </el-form-item>
      <el-alert title="Steam ID、EOS ID、完整用户 ID 至少填写一项；完整 ID 可直接从登录日志复制，支持 EOSPlus: 前缀。" type="info" :closable="false" style="margin-bottom:18px" />
      <el-form-item label="违规分类"><el-select v-model="manualForm.reason_code" style="width:100%"><el-option v-for="(label,code) in presets" :key="code" :label="label" :value="code" /></el-select></el-form-item>
      <el-form-item label="自定义理由（留空则使用预设文字）"><el-input v-model="manualForm.reason" type="textarea" :rows="3" maxlength="200" show-word-limit placeholder="填写具体行为、录像情况等" /></el-form-item>
    </el-form>
    <template #footer><el-button @click="addVisible=false">取消</el-button><el-button type="danger" :loading="adding" @click="submitManualAdd">确认加入黑名单</el-button></template>
  </el-dialog>

  <el-dialog v-model="editVisible" title="编辑黑名单档案" width="520px" destroy-on-close>
    <el-form label-position="top">
      <el-form-item label="玩家显示名称"><el-input v-model="editForm.name" maxlength="80" /></el-form-item>
      <el-form-item label="违规分类"><el-select v-model="editForm.reason_code" style="width:100%" @change="applyPreset"><el-option v-for="(label,code) in presets" :key="code" :label="label" :value="code" /></el-select></el-form-item>
      <el-form-item label="具体理由"><el-input v-model="editForm.reason" type="textarea" :rows="4" maxlength="200" show-word-limit placeholder="填写具体行为、录像情况等" /></el-form-item>
      <el-alert title="Steam / EOS 身份不会因为编辑名称或理由而改变" type="info" :closable="false" />
    </el-form>
    <template #footer><el-button @click="editVisible=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveEdit">保存修改</el-button></template>
  </el-dialog>

  <el-drawer v-model="detailVisible" title="玩家完整档案" size="440px">
    <template v-if="detailEntry">
      <div class="drawer-hero"><div class="drawer-name">{{ detailEntry.name }}</div><el-tag :type="reasonType(detailEntry.reason_code)" effect="dark">{{ presets[detailEntry.reason_code] || '其他' }}</el-tag></div>
      <dl class="detail-grid">
        <dt>具体理由</dt><dd>{{ detailEntry.reason || '未填写' }}</dd>
        <dt>Steam ID</dt><dd class="mono">{{ detailEntry.steam_id || '—' }} <el-button link :icon="DocumentCopy" @click="copyText(detailEntry.steam_id,'Steam ID')" /></dd>
        <dt>EOS ID</dt><dd class="mono">{{ detailEntry.eos_id || '—' }} <el-button link :icon="DocumentCopy" @click="copyText(detailEntry.eos_id,'EOS ID')" /></dd>
        <dt>完整用户 ID</dt><dd class="mono">{{ detailEntry.user_id || '—' }} <el-button link :icon="DocumentCopy" @click="copyText(detailEntry.user_id,'完整用户 ID')" /></dd>
        <dt>曾用名称</dt><dd>{{ detailEntry.aliases && detailEntry.aliases.length ? detailEntry.aliases.join('、') : '无' }}</dd>
        <dt>加入时间</dt><dd>{{ detailEntry.created_at || '—' }}</dd>
        <dt>最后更新</dt><dd>{{ detailEntry.updated_at || '—' }}</dd>
      </dl>
    </template>
  </el-drawer>
</div>
<script>
const { createApp,ref,reactive,computed,watch,onMounted } = Vue;
const { ElMessage,ElMessageBox } = ElementPlus;
const app=createApp({setup(){
  const entries=ref([]),presets=ref({}),checkToken=ref(''),updatedAt=ref('');
  const loading=ref(false),saving=ref(false),adding=ref(false),keyword=ref(''),reasonFilter=ref(''),sortMode=ref('updated_desc');
  const page=ref(1),pageSize=ref(15),addVisible=ref(false),editVisible=ref(false),detailVisible=ref(false),detailEntry=ref(null);
  const manualForm=reactive({manual:true,player:'',steam_id:'',user_id:'',reason_code:'quit_after_death',reason:''});
  const editForm=reactive({user_id:'',name:'',reason_code:'other',reason:''});
  async function api(url,options={}){
    options.headers=options.headers||{};const token=localStorage.getItem('gm_token');
    if(token) options.headers.Authorization='Bearer '+token;
    const res=await fetch(url,options);let data={};try{data=await res.json()}catch(e){}
    if(res.status===401){localStorage.removeItem('gm_token');ElMessage.warning('登录已失效，请重新登录');setTimeout(()=>location.href='/',500);throw new Error('未认证')}
    if(!res.ok||data.error) throw new Error(data.error||('HTTP '+res.status));return data;
  }
  async function fetchBlacklist(){loading.value=true;try{const d=await api('/api/gm/blacklist');entries.value=d.entries||[];presets.value=d.reason_presets||{};checkToken.value=d.check_token||'';updatedAt.value=d.updated_at||''}catch(e){ElMessage.error('读取黑名单失败：'+e.message)}finally{loading.value=false}}
  const filteredEntries=computed(()=>{const q=keyword.value.trim().toLocaleLowerCase();let list=entries.value.filter(e=>{if(reasonFilter.value&&e.reason_code!==reasonFilter.value)return false;if(!q)return true;return [e.name,e.user_id,e.steam_id,e.eos_id,e.reason,...(e.aliases||[])].join(' ').toLocaleLowerCase().includes(q)});return list.slice().sort((a,b)=>sortMode.value==='created_asc'?String(a.created_at||'').localeCompare(String(b.created_at||'')):sortMode.value==='name_asc'?String(a.name||'').localeCompare(String(b.name||''),'zh-CN'):String(b.updated_at||'').localeCompare(String(a.updated_at||'')))});
  const pageEntries=computed(()=>filteredEntries.value.slice((page.value-1)*pageSize.value,page.value*pageSize.value));
  const cheatCount=computed(()=>entries.value.filter(e=>['cheating','bug_abuse'].includes(e.reason_code)).length);
  const disruptionCount=computed(()=>entries.value.filter(e=>['quit_after_death','griefing','harassment'].includes(e.reason_code)).length);
  const recentCount=computed(()=>{const limit=Date.now()-7*86400000;return entries.value.filter(e=>{const t=Date.parse(String(e.updated_at||'').replace(' ','T'));return Number.isFinite(t)&&t>=limit}).length});
  watch([keyword,reasonFilter,sortMode,pageSize],()=>page.value=1);
  function clearFilters(){keyword.value='';reasonFilter.value='';sortMode.value='updated_desc'}
  function goBack(){location.href='/'}
  function firstChar(name){return String(name||'?').trim().slice(0,1).toUpperCase()||'?'}
  function shortId(id){id=String(id||'');return id.length>18?id.slice(0,8)+'…'+id.slice(-6):id||'—'}
  function reasonType(code){return ({cheating:'danger',bug_abuse:'danger',quit_after_death:'warning',griefing:'warning',harassment:'warning',other:'info'})[code]||'info'}
  async function copyText(text,label){if(!text){ElMessage.warning(label+'为空');return}try{await navigator.clipboard.writeText(String(text));ElMessage.success(label+'已复制')}catch(e){ElMessage.warning('复制失败，请手动复制')}}
  function openManualAdd(){Object.assign(manualForm,{manual:true,player:'',steam_id:'',user_id:'',reason_code:'quit_after_death',reason:''});addVisible.value=true}
  async function submitManualAdd(){
    if(!manualForm.player.trim()){ElMessage.warning('请填写玩家名称');return}
    if(!manualForm.steam_id.trim()&&!manualForm.user_id.trim()){ElMessage.warning('请至少填写一个 Steam/EOS 身份 ID');return}
    adding.value=true;
    try{const d=await api('/api/gm/blacklist/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(manualForm)});ElMessage.success('已手动拉黑 '+d.entry.name);addVisible.value=false;await fetchBlacklist()}
    catch(e){ElMessage.error('添加失败：'+e.message)}finally{adding.value=false}
  }
  function showDetail(entry){detailEntry.value=entry;detailVisible.value=true}
  function openEdit(entry){Object.assign(editForm,{user_id:entry.user_id,name:entry.name||'',reason_code:entry.reason_code||'other',reason:entry.reason||''});editVisible.value=true}
  function applyPreset(code){if(presets.value[code])editForm.reason=presets.value[code]}
  async function saveEdit(){if(!editForm.reason.trim()){ElMessage.warning('请填写具体理由');return}saving.value=true;try{await api('/api/gm/blacklist/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(editForm)});ElMessage.success('档案已更新');editVisible.value=false;await fetchBlacklist()}catch(e){ElMessage.error('更新失败：'+e.message)}finally{saving.value=false}}
  async function removeEntry(entry){try{await ElMessageBox.confirm('确定将【'+entry.name+'】从黑名单中移除吗？此操作会立即同步到进服器。','移除黑名单',{confirmButtonText:'确认移除',cancelButtonText:'取消',type:'warning'})}catch(e){return}try{await api('/api/gm/blacklist/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:entry.user_id})});ElMessage.success('已移出黑名单');await fetchBlacklist()}catch(e){ElMessage.error('移除失败：'+e.message)}}
  function exportJson(){const payload={exported_at:new Date().toISOString(),count:filteredEntries.value.length,entries:filteredEntries.value};const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='dread-hunger-blacklist-'+new Date().toISOString().slice(0,10)+'.json';a.click();URL.revokeObjectURL(url);ElMessage.success('已导出 '+filteredEntries.value.length+' 条记录')}
  onMounted(()=>{if(!localStorage.getItem('gm_token')){location.href='/';return}fetchBlacklist()});
  return{entries,presets,checkToken,updatedAt,loading,saving,adding,keyword,reasonFilter,sortMode,page,pageSize,addVisible,editVisible,detailVisible,detailEntry,manualForm,editForm,filteredEntries,pageEntries,cheatCount,disruptionCount,recentCount,fetchBlacklist,clearFilters,goBack,firstChar,shortId,reasonType,copyText,openManualAdd,submitManualAdd,showDetail,openEdit,applyPreset,saveEdit,removeEntry,exportJson,...ElementPlusIconsVue};
}});
app.use(ElementPlus,{locale:ElementPlusLocaleZhCn});for(const [key,c] of Object.entries(ElementPlusIconsVue))app.component(key,c);app.mount('#blacklist-app');
</script>
</body></html>'''



def make_handler(console: GMConsole):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DreadHungerGM/" + VERSION

        def log_message(self, fmt, *args):
            return

        def get_auth_token(self) -> str:
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return auth_header[7:].strip()
            cookies = self.headers.get("Cookie", "")
            for part in cookies.split(";"):
                part = part.strip()
                if part.startswith("gm_session="):
                    return part[len("gm_session=") :]
            return ""

        def is_authed(self) -> bool:
            token = self.get_auth_token()
            return console.valid_session(token)

        def send_bytes(self, data: bytes, ct: str, status: int = 200, headers: dict = None):
            self.send_response(status)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if headers:
                for k, val in headers.items():
                    self.send_header(k, val)
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, value, status=200):
            self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

        def send_html(self, html_str: str, status=200, headers=None):
            self.send_bytes(html_str.encode(), "text/html; charset=utf-8", status, headers)

        def redirect(self, url, headers=None):
            self.send_response(302)
            self.send_header("Location", url)
            if headers:
                for k, val in headers.items():
                    self.send_header(k, val)
            self.end_headers()

        def read_body(self) -> bytes:
            if hasattr(self, "_cached_body"):
                return self._cached_body
            length = int(self.headers.get("Content-Length", "0"))
            if length > 500_000 or length <= 0:
                self._cached_body = b""
            else:
                self._cached_body = self.rfile.read(length)
            return self._cached_body

        def get_params(self) -> dict:
            raw = self.read_body()
            if not raw:
                return {}
            try:
                data = json.loads(raw.decode("utf-8", "replace"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
            try:
                from urllib.parse import parse_qs
                qs = parse_qs(raw.decode("utf-8", "replace"))
                return {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
            except Exception:
                pass
            return {}

        def do_GET(self):
            route = urlsplit(self.path)
            path = route.path

            if path in ("/", "/gm"):
                self.send_html(app_html())

            elif path == "/blacklist":
                self.send_html(blacklist_html())

            elif path == "/logout":
                console.invalidate(self.get_auth_token())
                self.redirect("/", {"Set-Cookie": "gm_session=; Path=/; Max-Age=0"})

            elif path == "/api/gm/players":
                if not self.is_authed():
                    self.send_json({"error": "未授权"}, 401)
                    return
                self.send_json(console.get_players())

            elif path == "/api/gm/thralls":
                if not self.is_authed():
                    self.send_json({"error": "未授权"}, 401)
                    return
                self.send_json(console.get_thralls())

            elif path == "/api/gm/items":
                if not self.is_authed():
                    self.send_json({"error": "未授权"}, 401)
                    return
                self.send_json(console.get_items())

            elif path == "/api/gm/teleport_presets":
                if not self.is_authed():
                    self.send_json({"error": "未授权"}, 401)
                    return
                self.send_json(console.get_teleport_presets())

            elif path == "/api/gm/winning-card-reward":
                if not self.is_authed():
                    self.send_json({"error": "未授权"}, 401)
                    return
                self.send_json(console.get_winning_card_reward())

            elif path == "/api/gm/blacklist":
                if not self.is_authed():
                    self.send_json({"error": "未授权"}, 401)
                    return
                self.send_json(console.get_blacklist())

            elif path == "/api/gm/blacklist/check-lobby":
                if not self.is_authed():
                    self.send_json({"error": "未授权"}, 401)
                    return
                self.send_json(console.check_lobby_blacklist())

            elif path == "/api/blacklist/check-lobby":
                token = parse_qs(route.query).get("token", [""])[0]
                if not console.valid_blacklist_check_token(token):
                    self.send_json({"error": "黑名单查询令牌无效"}, 401)
                    return
                self.send_json(console.check_lobby_blacklist())

            else:
                self.send_json({"error": "Not found"}, 404)

        def do_POST(self):
            path = urlsplit(self.path).path

            if path == "/login":
                params = self.get_params()
                pwd = params.get("password", "")
                if console.check_password(str(pwd)):
                    token = console.create_session()
                    self.send_response(200)
                    self.send_header(
                        "Set-Cookie",
                        f"gm_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"
                    )
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    data = json.dumps({"ok": True, "token": token}, ensure_ascii=False).encode("utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_json({"error": "密码错误"}, 401)
                return

            if not self.is_authed():
                self.send_json({"error": "未授权"}, 401)
                return

            if path == "/api/gm/blacklist/add":
                try:
                    self.send_json(console.add_blacklist(self.get_params()))
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 400)
                return

            if path == "/api/gm/blacklist/remove":
                try:
                    self.send_json(console.remove_blacklist(self.get_params()))
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 400)
                return

            if path == "/api/gm/blacklist/update":
                try:
                    self.send_json(console.update_blacklist(self.get_params()))
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 400)
                return

            if path == "/api/gm/teleport_presets/save":
                try:
                    self.send_json(console.save_teleport_preset(self.get_params()))
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 400)
                return

            if path == "/api/gm/teleport_presets/remove":
                try:
                    self.send_json(console.remove_teleport_preset(self.get_params()))
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 400)
                return

            if path == "/api/gm/winning-card-reward":
                try:
                    self.send_json(console.save_winning_card_reward(self.get_params()))
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, 400)
                return

            actions = [
                "send_message", "end_game", "skip_poker", "open_armory", "kick_player",
                "revive_player", "teleport_to_ship", "give_item",
                "teleport_player", "execute_player",
            ]
            for action in actions:
                if path == f"/api/gm/{action}" or path == f"/{action}":
                    params = self.get_params()
                    try:
                        result = console.send_command(action, params)
                    except ValueError as exc:
                        self.send_json({"error": str(exc)}, 400)
                        return
                    status = 202 if result.get("queued") else (200 if result.get("success") else 409)
                    self.send_json(result, status)
                    return

            self.send_json({"error": "Not found"}, 404)

    return Handler



class GMHTTPServer(ThreadingHTTPServer):
    request_queue_size = 64
    daemon_threads = True
    allow_reuse_address = True


def discover_root(explicit: Optional[Path]) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    for candidate in [Path.cwd(), Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent]:
        if (candidate / "DreadHunger").is_dir() or (candidate / "Linux 插件").is_dir():
            return candidate.resolve()
    return Path.cwd().resolve()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Dread Hunger Linux GM 控制台")
    parser.add_argument("--root", type=Path, default=None, help="LinuxServer 目录 (默认自动从当前目录和脚本目录查找)")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9900, help="监听端口 (默认 9900)")
    parser.add_argument(
        "--password",
        default=os.environ.get("DH_GM_PASSWORD", DEFAULT_PASSWORD),
        help="登录密码；也可通过 DH_GM_PASSWORD 环境变量设置",
    )
    args = parser.parse_args(argv)

    root = discover_root(args.root)
    console = GMConsole(root, args.password)

    server = GMHTTPServer((args.host, args.port), make_handler(console))
    print(f"[GM控制台] Dread Hunger GM Console v{VERSION}")
    print(f"[GM控制台] 根目录: {root}")
    print(f"[GM控制台] 面板: http://{args.host}:{args.port}")
    print("[GM控制台] 认证: 已启用（密码不会写入日志）")
    print(f"[GM控制台] 指令文件: {console.command_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[GM控制台] 退出")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
