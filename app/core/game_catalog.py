"""Idle Mafia Game layout. Used so the app matches the real HUD, not a generic bot list."""

GAME_TABS = (
    "Safehouse",
    "Jobs",
    "Properties",
    "Inventory",
    "Collection",
    "Shop",
    "Fight",
    "Bank",
    "Operations",
    "Contracts",
    "Crew",
    "Bosses",
    "Family",
    "Territory",
    "Rankings",
    "Trade",
    "Heists",
)

# Only these left-rail toggles run Start / Targets. The rest stay off until they work.
READY_FEATURES = ("Jobs", "Family", "Shop", "Bank")


JOB_ZONES = (
    "NEW ASHPORT",
    "PORT CALDERA",
    "VOLKOVSK",
    "JADE HARBOR",
    "STERLING CROSS",
    "VEILMONT",
    "VESPERA",
)

JOB_ZONE_LEVELS = {
    "NEW ASHPORT": 1,
    "PORT CALDERA": 30,
    "VOLKOVSK": 54,
    "JADE HARBOR": 78,
    "STERLING CROSS": 102,
    "VEILMONT": 126,
    "VESPERA": 150,
}

# Same order as the in-game list: city → TIER N (LEVEL X+) → six jobs.
JOB_TIER_BOOK = (
    ("NEW ASHPORT", 1, 1, (
        "Keep Watch on the Corner",
        "Tag Rival Turf",
        "Boost a Parked Car",
        "Shake Down the Newsstand",
        "Fence Fake Watches",
        "Rough Up a Pickpocket",
    )),
    ("NEW ASHPORT", 2, 8, (
        "Hijack a Delivery Truck",
        "Run the Chop Shop Night Shift",
        "Bribe a Dock Inspector",
        "Rob the Pawn Shop Safe",
        "Forge Gallery Paintings",
        "Torch a Rival's Warehouse",
    )),
    ("NEW ASHPORT", 3, 18, (
        "Crack the Vault at First National",
        "Ambush the Kovac Convoy",
        "Rig the Union Election",
        "Heist the Museum Gala",
        "Silence a Witness",
        "Take Over the Waterfront",
    )),
    ("PORT CALDERA", 4, 30, (
        "Smuggle Contraband Past the Coast Guard",
        "Shake Down the Cane Fields",
        "Rig the Marina Boat Races",
        "Hijack a Smuggler's Speedboat",
        "Bribe the Harbor Master",
        "Rob the Gold Bullion Ferry",
    )),
    ("PORT CALDERA", 5, 42, (
        "Run a Convoy to the Rebels",
        "Blackmail the Governor's Aide",
        "Heist the Sugar Baron's Vault",
        "Sink a Rival Smuggler's Fleet",
        "Seize the Grand Pavilion",
        "Take Over the Island Trade",
    )),
    ("VOLKOVSK", 6, 54, (
        "Raid an Abandoned Supply Depot",
        "Fix the Underground Boxing Circuit",
        "Shake Down the Icehouse District",
        "Bribe the Rail Yard Commissar",
        "Steal Kovac's Ice Trucks",
        "Torch the Kolyev Social Club",
    )),
    ("VOLKOVSK", 7, 66, (
        "Rob the State Bank of Volkovsk",
        "Ambush the Diamond Courier Train",
        "Silence the Prosecutor General",
        "Heist the Winter Palace Auction",
        "Break the Kovac Blockade",
        "Take Over the Volkovsk Underworld",
    )),
    ("JADE HARBOR", 8, 78, (
        "Smuggle Jade Through Customs",
        "Fix the Dragon Den Prizefights",
        "Shake Down the Night Market",
        "Hijack a Freighter of Counterfeits",
        "Bribe the Jade Court Captains",
        "Rob the Golden Lotus Vault",
    )),
    ("JADE HARBOR", 9, 90, (
        "Steal the Emperor's Jade Seal",
        "Ambush the Jade Court Summit",
        "Heist the Floating Palace",
        "Silence the Dragon Head's Heir",
        "Burn the Rival Fleet at Anchor",
        "Take Over Jade Harbor",
    )),
    ("STERLING CROSS", 10, 102, (
        "Pay Off the Precinct Captains",
        "Burgle the Records Hall",
        "Blackmail a City Councilman",
        "Steal the Court Docket",
        "Plant a Story in the Morning Herald",
        "Rig the Council Election",
    )),
    ("STERLING CROSS", 11, 114, (
        "Buy Off the Star Witness",
        "Break Into the Chancellery Archive",
        "Bribe the Supreme Bench",
        "Swap the Mint's Bullion",
        "Seize the Sterling Ledgers",
        "Claim the Charter Seat",
    )),
    ("VEILMONT", 12, 126, (
        "Bribe the Mountain Toll Wardens",
        "Smuggle Gold Over the High Pass",
        "Forge a Numbered Account",
        "Rob the Alpine Gold Train",
        "Intercept the Courier Cables",
        "Buy a Seat at the Chamber Table",
    )),
    ("VEILMONT", 13, 138, (
        "Crack the Numbered Vaults",
        "Counterfeit the Chamber Seals",
        "Ransom the Vault Governor's Keys",
        "Derail the Chairman's Express",
        "Freeze the Chamber's Accounts",
        "Take the Chairman's Seat",
    )),
    ("VESPERA", 14, 150, (
        "Bribe the Old Harbor Master",
        "Steal the Ferryman's Ledger",
        "Shake Down the Olive Press Barons",
        "Rob the Cliffside Courier",
        "Extort the Procession Road Tolls",
        "Buy an Audience with the Elders",
    )),
    ("VESPERA", 15, 162, (
        "Turn the First Family's Capos",
        "Raid the First Family's Treasury",
        "Steal the Book of Oaths",
        "Corner the Marble Quarries",
        "Expose the Elder Council's Secrets",
        "Take the First Seat",
    )),
)


def job_tier_heading(tier: int, level: int) -> str:
    return f"TIER {tier} (LEVEL {level}+)"


def zone_heading(name: str) -> str:
    level = JOB_ZONE_LEVELS.get(name)
    if level is None:
        return name
    return f"{name} (LEVEL {level}+)"
