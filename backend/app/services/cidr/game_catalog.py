"""Static game filter catalog (subset ported from AdminAntizapret GAME_FILTER_CATALOG)."""

GAME_FILTER_CATALOG: list[dict] = [
    {"key": "lol", "title": "League of Legends", "subtitle": "Riot Games", "domains": ["riotgames.com", "leagueoflegends.com", "pvp.net"], "server_ips": []},
    {"key": "valorant", "title": "VALORANT", "subtitle": "Riot Games", "domains": ["playvalorant.com", "riotgames.com"], "server_ips": []},
    {"key": "dota2", "title": "Dota 2", "subtitle": "Valve", "domains": ["dota2.com", "steampowered.com"], "server_ips": []},
    {"key": "cs2", "title": "Counter-Strike 2", "subtitle": "Valve", "domains": ["counter-strike.net", "steampowered.com"], "server_ips": []},
    {"key": "steam_platform", "title": "Steam", "subtitle": "Valve", "domains": ["steampowered.com", "steamcommunity.com", "steamcontent.com"], "server_ips": []},
    {"key": "world_of_warcraft", "title": "World of Warcraft", "subtitle": "Blizzard", "domains": ["worldofwarcraft.com", "battle.net"], "server_ips": []},
    {"key": "overwatch2", "title": "Overwatch 2", "subtitle": "Blizzard", "domains": ["playoverwatch.com", "battle.net"], "server_ips": []},
    {"key": "apex_legends", "title": "Apex Legends", "subtitle": "EA", "domains": ["ea.com", "respawn.com"], "server_ips": []},
    {"key": "world_of_tanks", "title": "World of Tanks", "subtitle": "Wargaming", "domains": ["worldoftanks.com", "wargaming.net"], "server_ips": []},
    {"key": "roblox", "title": "Roblox", "subtitle": "Roblox Corp", "domains": ["roblox.com", "rbxcdn.com"], "server_ips": []},
    {"key": "minecraft", "title": "Minecraft", "subtitle": "Mojang", "domains": ["minecraft.net", "mojang.com"], "server_ips": []},
    {"key": "fortnite", "title": "Fortnite", "subtitle": "Epic Games", "domains": ["epicgames.com", "fortnite.com"], "server_ips": []},
    {"key": "genshin", "title": "Genshin Impact", "subtitle": "HoYoverse", "domains": ["hoyoverse.com", "mihoyo.com"], "server_ips": []},
    {"key": "pubg", "title": "PUBG", "subtitle": "Krafton", "domains": ["pubg.com", "krafton.com"], "server_ips": []},
    {"key": "faceit", "title": "FACEIT", "subtitle": "FACEIT", "domains": ["faceit.com"], "server_ips": []},
]

GAME_BLOCK_START = "# BEGIN game-filters (AdminPanelAZ)"
GAME_BLOCK_END = "# END game-filters (AdminPanelAZ)"
GAME_IP_BLOCK_START = "# BEGIN game-filter-ips (AdminPanelAZ)"
GAME_IP_BLOCK_END = "# END game-filter-ips (AdminPanelAZ)"
