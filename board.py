# 五子棋棋盘类
# 提供落子、判断是否胜利功能


class chessBoard:
    def __init__(self):
        self.__col = 15                                                                  # 15*15棋盘
        self.board = [[-1] * (self.__col + 1) for i in range(0, self.__col + 1)]                 # 未落子时棋盘初始化为-1
        self.__num = 0                                                                   # 初始化当前棋子数
        self.last_draw = -1                                                               # 上一个走棋者棋子的颜色
        self.__last = (-1, -1)                                                           # 本地记录上一次走棋的位置

    # 检查四个方向看是否满足胜利条件
    # @color: 1-黑棋，0-白棋
    def __checkWin(self, x, y, color):
        # 上下方向
        tmpY = y
        while tmpY > 0 and self.board[x][tmpY - 1] == color:
            tmpY -= 1
        cnt = 0
        while tmpY < self.__col and self.board[x][tmpY] == color:
            cnt += 1
            tmpY += 1
            if cnt == 5:
                return True
        # 左右方向
        tmpX = x
        while tmpX > 0 and self.board[tmpX - 1][y] == color:
            tmpX -= 1
        cnt = 0
        while tmpX < self.__col and self.board[tmpX][y] == color:
            tmpX += 1
            cnt += 1
            if cnt == 5:
                return True
        # 左上-右下方向
        tmpX = x
        tmpY = y
        while tmpX > 0 and tmpY > 0 and self.board[tmpX - 1][tmpY - 1] == color:
            tmpY -= 1
            tmpX -= 1
        cnt = 0
        while tmpY < self.__col and tmpX < self.__col and self.board[tmpX][tmpY] == color:
            tmpY += 1
            tmpX += 1
            cnt += 1
            if cnt == 5:
                return True
        # 右上-左下方向
        tmpX = x
        tmpY = y
        while tmpY < self.__col and tmpX > 0 and self.board[tmpX - 1][tmpY + 1] == color:
            tmpY += 1
            tmpX -= 1
        cnt = 0
        while tmpY > 0 and tmpX < self.__col and self.board[tmpX][tmpY] == color:
            tmpY -= 1
            tmpX += 1
            cnt += 1
            if cnt == 5:
                return True
        # 都不满足条件
        return False

    # 走棋
    # 棋盘满返回-2，落子位置错误返回-1，正常落子返回0，胜负已分返回1
    def move(self, x, y, color):
        # 棋盘已满
        if self.__num == self.__col * self.__col:
            return -2
        x = int(x)
        y = int(y)
        # 要落子的位置已经有子或者超出棋盘范围
        if x > self.__col or x < 0 or y > self.__col or y < 0 or self.board[x][y] != -1:
            return -1
        # 正常落子
        self.last_draw = color                       # 记录悔棋信息
        self.__last = (x, y)                        # 更新上一步走棋
        self.board[x][y] = color
        self.__num += 1
        if self.__checkWin(x, y, color):
            return 1
        return 0

    # 悔棋，用于修正接收到的棋子，主要由服务器使用
    def withdraw(self, x, y):
        x = int(x)
        y = int(y)
        self.board[x][y] = -1
        if self.last_draw == 1:
            self.last_draw = 0
        else:
            self.last_draw = 1
        self.__num -= 1

    # 撤回*本地保存*的上一步棋
    def undo(self):
        x = self.__last[0]
        y = self.__last[1]
        self.board[x][y] = -1
        if self.last_draw == 1:
            self.last_draw = 0
        else:
            self.last_draw = 1
        self.__num -= 1

    # 获取本地保存的上一步棋
    def last_step(self):
        return self.__last

    # 获取棋盘上的棋子数
    def number(self):
        return self.__num

    # 清空棋盘
    def clear(self):
        self.board = [[-1] * self.__col for i in range(0, self.__col)]  # 未落子时棋盘初始化为-1
        self.__num = 0  # 初始化当前棋子数


# 测试函数
if __name__ == '__main__':
    b = chessBoard()
    while(True):
        (x, y, z) = input()
        print(b.move(x, y, z))

