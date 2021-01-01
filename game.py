import board


# game数据结构
# 默认第一个人拿0-白棋，第二个人拿1-黑棋
class game():
    def __init__(self, game_name):
        self.name = game_name
        self.board = board.chessBoard()
        self.usr1 = -1
        self.usr2 = -1
        self.num = 0

    # 返回查询用户对手的id
    def get_oppo(self, plyr):
        if plyr == self.usr1:
            return self.usr2
        elif plyr == self.usr2:
            return self.usr1
        else:
            return -1

    # 返回查询用户棋子的颜色
    def get_color(self, plyr):
        if plyr == self.usr1:
            return 0
        elif plyr == self.usr2:
            return 1
        else:
            return -1

    # 返回棋局中玩家数目
    def state(self):
        return self.num

    # 向棋局增加玩家
    def add(self, plyr):
        if self.usr1 == -1:
            self.usr1 = plyr
        elif self.usr2 == -1 and self.usr1 != plyr:
            self.usr2 = plyr
        self.num += 1

    # 输出棋局名
    def get_name(self):
        return self.name

    # 清空棋盘
    def clear_board(self):
        self.board.clear()

    # 踢人, 清空整个棋局
    def kick(self):
        self.__init__(self.name)