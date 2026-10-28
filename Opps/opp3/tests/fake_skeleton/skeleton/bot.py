class Bot():
    def handle_new_round(self, game_state, round_state, active): raise NotImplementedError
    def handle_round_over(self, game_state, terminal_state, active): raise NotImplementedError
    def get_action(self, game_state, round_state, active): raise NotImplementedError
