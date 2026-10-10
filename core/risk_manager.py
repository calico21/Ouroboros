from config.apex_basket_config import ACCOUNT

class ApexRiskManager:
    """Gestiona el Trailing Ratchet y el dimensionamiento Cushion-Aware + Sprint."""
    def __init__(self):
        self.balance = ACCOUNT["starting_balance"]
        self.floor = ACCOUNT["initial_floor"]
        self.buffer = ACCOUNT["buffer"]
        self.lock_hwm = ACCOUNT["lock_hwm"]
        self.lock_floor = ACCOUNT["lock_floor"]
        self.target = ACCOUNT["profit_target"]
        self.is_frozen = False

    def update_ratchet(self, intra_peak_mfe):
        """Actualiza el suelo móvil en base al pico intra-trade."""
        if intra_peak_mfe >= self.lock_hwm:
            self.floor = self.lock_floor
            self.is_frozen = True
        elif not self.is_frozen:
            self.floor = max(self.floor, intra_peak_mfe - self.buffer)

    def register_trade(self, net_pnl, mfe_usd):
        intra_peak = self.balance + mfe_usd
        self.update_ratchet(intra_peak)
        self.balance += net_pnl
        cushion = self.balance - self.floor
        is_breach = self.balance <= self.floor
        is_pass = self.balance >= self.target
        return cushion, is_breach, is_pass

    def get_position_sizing(self, asset_cfg):
        cushion = self.balance - self.floor
        if self.is_frozen:
            return asset_cfg["contracts_sprint"]
        elif cushion < 1300.0:
            return asset_cfg["contracts_defense"]
        else:
            return asset_cfg["contracts_normal"]
