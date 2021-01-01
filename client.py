from socketserver import DatagramRequestHandler as drh
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import socket
import socketserver
import time
import queue
import threading
import scoreboard_u
import sys
import board

# 全局发消息
host = 'localhost'
server_port = 8888  # 已知的服务器收信端口
buf_size = 1024

my_rcv_port = 7778              # 专门用来监听消息的绑定端口
client_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# 当前相关参数
id = -1                     # 服务器分配的唯一用户id
color = -1                  # 在当前某局中所持棋子颜色
board = board.chessBoard()  # 当前棋盘
sq = queue.Queue()          # 服务器发来的走棋消息队列
lock = threading.Lock()       # 对走棋消息队列的互斥锁


# 客户端通信UDP
class cliUDP(drh):
    def handle(self):
        print('server\'s address: ', self.client_address)
        # 指定接收端口，一直保持监听
        while True:
            data = self.rfile.readline()
            if data:
                print("msg from server")
                break
        msg = data.decode('utf-8')

        # 通讯机制进行处理
        # 获取互斥锁，放入消息队列
        if lock.acquire():
            sq.put(msg)
            lock.release()


# 客户端通讯线程，监听服务器主动发来的消息并应答
class client_rcv_thread(QThread):
    def __init__(self):
        super(QThread, self).__init__()
        # client
        self.host = 'localhost'
        self.rcv_addr = (self.host, my_rcv_port)  # 接收消息的地址
        print(self.rcv_addr)
        self.client_rcv = socketserver.UDPServer(self.rcv_addr, cliUDP)

    def run(self):
        self.client_rcv.serve_forever()  # 保持监听等待服务器发消息
        

# 处理服务器回复信息的信号类
class colorSignal(QThread):
    signal = pyqtSignal(int)        # 棋子颜色变化的信号量，由gamelist窗体调用并释放

    def __init__(self):
        super().__init__()
        self.color = -1

    def setcolor(self, c):
        self.color = c

    def run(self):
        if self.color != -1:
            self.signal.emit(self.color)



# 处理服务器主动发来信息的信号类
class serverSignal(QThread):
    signal = pyqtSignal(str)      # 对服务器发来的信息进行转发，待槽函数处理后分发给对应的函数
    msg = pyqtSignal(str)         # 需要打印的消息单独处理

    def run(self):
        while True:
            time.sleep(1)
            if lock.acquire():
                while not sq.empty():
                    s = sq.get()
                    self.signal.emit(s)
                lock.release()


# 向服务器发消息，使用操作系统随机分配的端口，收到1次回复后退出
def send(msg):
    # 未登录发消息，拒绝发送
    # print('send\'s id:'+str(id))
    if id == -1 and msg[0] == '-':
        print("not login！")
        return "-2"                                          # not login未登录错误
    # 已分配id时自动给消息加头
    if id != -1:
        if msg[0] != '-':
            msg = '-' + msg
        msg = '-' + str(id) + msg
    srv_addr = (host, server_port)  # 服务器地址
    client_send.sendto(msg.encode('utf-8'), srv_addr)
    data, saddr = client_send.recvfrom(buf_size)
    if not data:
        return "-1"                                          # message error 空消息错误
    print('I rcved: ' + data.decode('utf-8'))
    return data.decode('utf-8')


# 登陆
def login(player_name):
    global id                   # 否则改不了id
    rcv_id = send(player_name+'-'+str(my_rcv_port))      # 发送自己的固定接收端口
    # 对信息发送的回应做错误处理，以下同理
    if not rcv_id.isdigit():
        return "-3"
    id = int(rcv_id)
    return id


# 进入选中的棋局,获取分配的棋子颜色
def join(game_name):
    global color
    msg = '-g-' + game_name
    i = send(msg)
    if i == '1' or i == '0':
        color = int(i)
    elif i == '-1':                 # 选择了一个满的游戏
        color = -2
    else:
        color = -1
    return color


# 自己走棋
def move(x, y):
    msg = '-m-' + str(x) + '-' + str(y)
    i = send(msg)
    if i == 'y':
        board.move(x, y, color)             # 更新自己棋盘
    return i


# 要求重新开始
def restart():
    msg = '-r'
    i = send(msg)
    if i != 'y':
        print("error restart")
        return '-1'
    board.clear()                   # 获得同意，清空棋盘重新开始
    return '0'


# 要求悔棋
def withdraw():
    x, y = board.last_step()
    msg = '-w' + '-' + str(x) + '-' + str(y)
    i = send(msg)
    if i == 'y':
        board.withdraw(x, y)
        return '0'
    else:
        return '-1'


# 要求离开游戏
def leave():
    global color
    msg = '-l'
    i = send(msg)
    if i == 'y':
        color = -1
        board.clear()
    return i


# 列出当前正在比赛的棋局
def games():
    msg = '-lg'
    return send(msg)


# 列出服务器的当前所有玩家列表，及其参加棋局的情况
def list():
    msg = '-lu'
    return send(msg)


# 游戏主界面GUI
class cBoard_Ui(QMainWindow):
    def __init__(self):
        super().__init__()
        player = self.login()
        if player != '_failed':
            self.setupUi(player)

            self.myturn = False
        else:
            return

    def setupUi(self, player):
        # 设置静态GUI
        self.setObjectName("GoBang")
        self.resize(710, 740)
        self.drawed_piece = 0                                                # 棋盘中已画出的棋子数
        self.setWindowIcon(QIcon("./r.jpg"))
        self.client_rcv = client_rcv_thread()
        self.client_rcv.start()  # 启动接受服务器消息线程
        self.server_msg = serverSignal()  # GUI对服务器主动发来的信息统一进行处理
        self.server_msg.start()
        self.centralwidget = QWidget(self)
        self.centralwidget.setObjectName("centralwidget")
        self.board = QLabel(self.centralwidget)
        self.board.setScaledContents(True)
        self.board.setObjectName("Board")
        self.board.setGeometry(QRect(0, 0, 710, 710))
        self.board.setAutoFillBackground(False)
        self.board.setText("")
        self.board.setPixmap(QPixmap("./board.bmp"))
        self.board.setScaledContents(True)
        self.setCentralWidget(self.centralwidget)
        # 设置菜单栏
        menubar = self.menuBar()
        self.setWindowTitle("GoBang!")
        self.list_game1 = menubar.addAction("Player: "+player)
        login = menubar.addAction("Log In")
        list_game = menubar.addAction("List Game")
        list_users = menubar.addAction("List Users")
        restart = menubar.addAction("Restart")
        withdraw = menubar.addAction("Withdraw")
        leave = menubar.addAction("Leave")
        # 连接信号与槽函数
        login.triggered.connect(self.login)
        list_game.triggered.connect(self.listgame)
        list_users.triggered.connect(self.listusr)
        restart.triggered.connect(self.restart_game)
        leave.triggered.connect(self.leave_game)
        withdraw.triggered.connect(self.withdraw)

        # 连接服务器信息处理函数
        self.server_msg.signal.connect(self.rcv)

        # 初始化棋盘
        # 预先读取黑白子图片
        self.pieceW = QPixmap("./w.png")
        self.pieceB = QPixmap("./b.png")
        # 管理棋子的列表
        self.pieces = []
        for i in range(225):
            piece = QLabel(self)
            piece.setScaledContents(True)
            self.pieces.append(piece)
        QMetaObject.connectSlotsByName(self)

    # 处理服务器发来的字符串s，起到handle函数的作用
    def rcv(self, msg):
        global color                                        # 退出时把棋子颜色重新修改为-1
        # 如果是服务器转发的对方消息
        if msg[0] == '-':
            s = msg.split('-')
            oppo = s[1]  # 对手id
            op = s[2]
            # 接收服务器发来的对方走棋,("-id-m-x-y")
            if op == 'm':
                x = int(s[3])
                y = int(s[4])
                if color == 1:
                    c = 0
                else:
                    c = 1
                board.move(x, y, c)
                self.draw(x, y, c)   # 在棋盘上画子
                self.myturn = True        # 解锁己方棋盘，可以下棋
                print('oppo move', s)
            # 接收服务器发来的对方悔棋,("-id-w-x-y")
            if op == 'w':
                x = int(s[3])
                y = int(s[4])
                if board.last_draw == color:  # 如果自己已经下了棋，先退回自己的上一步
                    board.undo()
                    self.pieces[board.number()].clear()
                    self.drawed_piece -= 1
                board.withdraw(x, y)
                self.pieces[board.number()].clear()
                self.drawed_piece -= 1
                self.myturn = False                             # 锁棋盘，重新等待对方下棋
            # 接收服务器发来的对方已经退出,("-id-l")
            elif op == 'l':
                r = QMessageBox.question(self, 'Oops', "Your opponent has dropped. Clear the board?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if r == QMessageBox.Yes:
                    self.clear_game()
                    board.clear()
                self.myturn = False                                     # 锁棋盘
                color = -1
                print("oppo quit")
            # 接收服务器发来的对方要求重开，("-id-r")
            elif op == 'r':
                # r = input("对手要求重新开始游戏，是否同意？y/n")  # 需要GUI进一步处理
                r = QMessageBox.question(self, 'Oops', "Your opponent asked to restart the game. Agree?",
                                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                self.myturn = False                                     # 锁棋盘，必须先处理消息
                # 同意/不同意
                if r == QMessageBox.Yes:
                    rply = '-y-' + oppo
                    board.clear()
                    self.clear_game()
                else:
                    rply = '-n-' + oppo
                send(rply)

        # 服务器主动发来的消息，需要解析
        elif msg[0] == '~':
            m = msg.split('~')
            op = m[1]
            ex = "CANNOT CONTINUE:\n"
            # 只需要打印消息的处理
            if op == 'm' or op == 'p':
                if op == 'm':
                    ex = m[2]
                # 收到游戏开始消息（只有白棋会收到这个消息），提示但不必开始键盘
                elif op == 'p':
                    ex = 'GAME START! WAIT YOUR OPPONENT PLAY..'
                r = QMessageBox.information(self, 'Recieved', ex, QMessageBox.Ok)
                if r == QMessageBox.Ok:
                    print(ex)
            # 需要用户决定是否清空棋盘
            else:
                color = -1
                if op == 'c':
                    ex += "THE GAME IS CLOSED."
                elif op == 'k':
                    ex += "YOU HAVE BEEN KICKED OUT."
                elif op == 'o':
                    ex += "YOUR OPPONENT HAS BEEN KICKED OUT."
                elif op == 'l':
                    ex += 'YOU LOOOOOOSE!!'
                    self.myturn = False
                r = QMessageBox.question(self, 'Game Canceled', ex+"\nDo you want to clear the board?",
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if r == QMessageBox.Yes:
                    self.clear_game()


    # 退出游戏，清空本地画出的棋盘
    def clear_game(self):
        for i in range(self.drawed_piece):
            self.pieces[i].clear()
        self.drawed_piece = 0

    # 开始游戏
    def start(self, c):
        # 只有当已经成功获取棋子颜色时才会发射信号，因此不用做异常处理
        # 拿到白棋，后手，等待对方下棋
        if c == 0:
            self.myturn = False
        # 黑棋先走
        else:
            self.myturn = True
            r = QMessageBox.information(self, 'Game Start', 'Please move', QMessageBox.Ok)
            if r == QMessageBox.Ok:                                 # 必须点确认才能开始游戏！
                pass                                              # 需要完善


    # 下棋相关函数
    # 棋盘物理-逻辑转换函数, 判断物理坐标是否在可落子范围内
    # 范围合法返回逻辑坐标，不合法返回空
    # 11,38 step46
    def pixel2logal(self, x, y):
        x -= 32
        y -= 62
        tx = x % 46
        ty = y % 46
        lx = -1               # 先设置为不可能值
        ly = -1
        if tx <= 18 or (x <= 0 and tx >= 36):
            lx = int(x / 46)
        elif tx >= 36:
            lx = int(x / 46) + 1
        if ty <= 18 or (y <= 0 and ty >= 36):
            ly = int(y / 46)
        elif ty >= 36:
            ly = int(y / 46) + 1
        return lx, ly


    # 棋盘逻辑-物理转换函数
    def logal2pixel(self, x, y):
        # 检查输入合法
        if x in range(0, 15) and y in range(0, 15):
            return x * 46 + 11, y * 46 + 38
        return None, None


    # 在棋盘上画棋子
    def draw(self, lx, ly, c):
        x, y = self.logal2pixel(lx, ly)
        self.pieces[self.drawed_piece].setGeometry(x, y, 46, 46)
        if c == 0:
            self.pieces[self.drawed_piece].setPixmap(self.pieceW)
        else:
            self.pieces[self.drawed_piece].setPixmap(self.pieceB)
        self.drawed_piece += 1

    # 鼠标点击下棋
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.myturn:
            x, y = e.x(), e.y()                                         # 鼠标坐标
            # 判断落子位置是否合法，若合法则画上棋子并向服务器发消息
            lx, ly = self.pixel2logal(x, y)
            if lx >= 0 and ly >= 0:
                if board.board[lx][ly] == -1:                               # 如果该位置还没有棋子
                    rply = move(lx, ly)                                     # 向服务器发走棋信息
                    self.myturn = False                                     # 下完棋锁住棋盘，等待服务器消息
                    # 处理服务器返回的信息
                    if rply == 'y':                                         # 成功走棋
                        self.draw(lx, ly, color)                            # 在自己的棋盘上画子
                    elif rply == 'vy':                                      # 下棋后胜利
                        self.draw(lx, ly, color)                            # 在自己的棋盘上画子
                        r = QMessageBox.information(self, 'Win', "Congratulations!", QMessageBox.Ok)
                        if r == QMessageBox.Ok:
                            return

    # 重载默认关闭事件-点叉等同点leave退出
    def closeEvent(self, a0: QCloseEvent):
        # 已登录默认关闭事件等同退出，否则直接关闭窗体
        if id != -1:
            self.leave_game()
        client_send.close()


    # 槽函数
    # 用户登录
    def login(self):
        global host
        # 为了便于测试，要求输入服务器IP地址
        d2 = QInputDialog()
        d2.resize(500, 300)
        text, ok = d2.getText(self, "IP address", "Server IP: ", QLineEdit.Normal, "")
        if ok and text != '':
            host = text
        else:
            self.close()
            return '_failed'
        # 获取用户输入的用户名，并向服务器发送登录信息
        dialog = QInputDialog()
        dialog.resize(500, 300)
        text, ok = dialog.getText(self, "Log In", "Your name: ", QLineEdit.Normal, "")
        if ok and text != '':
            ans = login(text)
            if ans != '-3':
                r = QMessageBox.information(self, 'Logged', "Your ID is: " + str(ans), QMessageBox.Ok)
            else:
                r = QMessageBox.information(self, 'Error', "Error id from the server!", QMessageBox.Ok)
            if r == QMessageBox.Ok:
                return text
        else:
            self.close()
            return '_failed'


    # 获取游戏列表
    # 格式：游戏名，用户1，用户2
    def listgame(self):
        list = games()                                              # 发送消息并获取服务器发来的标准格式游戏列表
        if list:
            self.game_list_window = GameListUi(list, self)     # 游戏开始信号量作为参数传给子窗体
            self.game_list_window.show()
        else:
            self.deal_error(list)

    # 获取用户列表
    # 格式：用户名，用户积分，用户所在棋局
    def listusr(self):
        usr = list()
        if usr:
            self.scoreboard = scoreboard_u.ScoreBoardUi(usr)
            self.scoreboard.show()
        else:
            self.deal_error(usr)

    # 重新开始游戏
    def restart_game(self):
        ans = restart()
        # 对手同意重新开始，清空棋盘
        if ans == '0':
            for i in range(225):
                if self.pieces[i]:
                    self.pieces[i].clear()
                else:
                    break
        # 对手拒绝
        elif ans == '-1':
            r = QMessageBox.information(self, 'Rejected', "Your opponent refused to restart!",
                                       QMessageBox.Ok)
            if r == QMessageBox.Ok:
                return
        # 未知错误
        else:
            self.deal_error(ans)

    # 离开游戏
    def leave_game(self):
        # 警告信息
        buttonReply = QMessageBox.question(self, 'Warning', "Do you want to leave?",
                                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        # 用户确认，发送离开消息
        if buttonReply == QMessageBox.Yes:
            # 如果当前棋局已经退出，清空棋盘即可
            if color == -1:
                # ans = leave()
                self.clear_game()
            else:
                ans = leave()
                if ans == 'y':
                    r = QMessageBox.information(self, 'Successful Left', "The board is going to be cleared", QMessageBox.Ok)
                    if r == QMessageBox.Ok:
                        self.clear_game()                           # 清空本地棋盘，但不会关闭窗体
                elif ans != 'ny':                               # 未登录退出什么都不做
                    self.deal_error(ans)                        # 其他错误报未知错

    # 悔棋
    def withdraw(self):
        # 警告信息
        buttonReply = QMessageBox.question(self, 'Warning', "Do you want to withdraw?",
                                                     QMessageBox.Yes | QMessageBox.No,
                                                     QMessageBox.No)
        # 用户确认，发送请求悔棋信息
        if buttonReply == QMessageBox.Yes:
            x, y = board.last_step()                                # 获取本地保存的上一步
            ans = withdraw()
            if ans == '0':
                self.pieces[board.number()].clear()             # 注意返回该消息时棋盘已经把该逻辑棋子删掉了，因此要在得到的棋子数上再+1
                self.drawed_piece -= 1                              # 已经画出的棋子数-1
                self.myturn = True
                self.update()
                r = QMessageBox.information(self, 'Accepted', "Successful withdraw!", QMessageBox.Ok)
                if r == QMessageBox.Ok:
                    pass
            # 悔棋失败
            else:
                r = QMessageBox.information(self, 'Rejected', "You can't withdraw now!", QMessageBox.Ok)
                if r == QMessageBox.Ok:
                    pass

    # 错误处理弹窗
    def deal_error(self, errcode):
        # not login未登录错误
        if errcode == '-2':
            r = QMessageBox.information(self, 'Error', "You have to login first!", QMessageBox.Ok)
        # message error 空消息错误
        elif errcode == '-1':
            r = QMessageBox.information(self, 'Error', "You recieve a null msg from the server!", QMessageBox.Ok)
        # 未知错误
        else:
            r = QMessageBox.information(self, 'Error', "Unknown Error", QMessageBox.Ok)
        if r == QMessageBox.Ok:
            return


class GameListUi(QWidget):
    def __init__(self, gamestr, main):
        super().__init__()
        self.setupUi(gamestr)
        self.color = colorSignal()
        self.main = main

    def setupUi(self, gamestr):
        # 设置静态GUI
        self.setObjectName("GameList")
        self.resize(650, 450)
        self.game_list = QTableView(self)
        self.game_list.setGeometry(QRect(30, 100, 500, 320))
        self.game_list.setObjectName("game_list")
        self.game_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.game_list.model = QStandardItemModel()
        self.game_list.model.setHorizontalHeaderLabels(['Game Name', 'White', 'Black'])
        self.game_list.setModel(self.game_list.model)
        self.game_list.horizontalHeader().setStretchLastSection(True)
        self.game_list.setSelectionBehavior(QAbstractItemView.SelectRows)  # 设置整行选中
        self.join_button = QPushButton(self)
        self.join_button.setGeometry(QRect(550, 380, 80, 40))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(11)
        self.join_button.setFont(font)
        self.join_button.setObjectName("join_button")

        # 调整字体参数
        self.label = QLabel(self)
        self.label.setGeometry(QRect(210, 30, 150, 50))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(18)
        font.setBold(True)
        font.setWeight(75)
        self.label.setFont(font)
        self.label.setObjectName("label")
        self.setWindowTitle("Game List")
        self.join_button.setText("Join")
        self.label.setText("Games")

        # 把接收到的游戏列表切分输出到表格
        # 格式：游戏名，用户1，用户2.
        # gamestr = 'g,n1,n2.'
        splt = gamestr.split('.')
        row = 0
        for game in splt:
            s = game.split(',')
            if len(s) == 3:
                item1 = QStandardItem(s[0])
                item2 = QStandardItem(s[1])
                item3 = QStandardItem(s[2])
                self.game_list.model.setItem(row, 0, item1)
                self.game_list.model.setItem(row, 1, item2)
                self.game_list.model.setItem(row, 2, item3)
                row += 1
        self.join_button.clicked.connect(self.join_game)

    # 槽函数，点击join加入选中的游戏
    def join_game(self):
        g = self.game_list.selectedIndexes()
        if g:
            buttonReply = QMessageBox.question(self, 'Join', "Join game " + g[0].data() + "?",
                                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if buttonReply == QMessageBox.Yes:
                c = join(g[0].data())

                if c == 1:                                              # 正常加入游戏，并获取了黑棋，可以立刻开始
                    r = QMessageBox.information(self, 'Join', "Game Start!", QMessageBox.Ok)
                    if r == QMessageBox.Ok:
                        self.close()                                              # 关闭list窗体
                elif c == 0:                                              # 正常加入游戏，并获取了白棋,等待另一个人加入
                    r = QMessageBox.information(self, 'Join', "Successful access, wait for another player!", QMessageBox.Ok)
                    if r == QMessageBox.Ok:
                        self.close()                                        # 关闭list窗体
                # 用户选择了一个满的游戏
                elif c == -2:
                    print("hit color")
                    r = QMessageBox.information(self, 'Error', "You've chosen a full game!", QMessageBox.Ok)
                    if r == QMessageBox.Ok:
                        color = -1
                # 如果获取了正确的棋子颜色，正常开始游戏
                if c == 0 or c == 1:
                    self.color = colorSignal()
                    self.color.setcolor(c)
                    self.color.signal.connect(self.main.start)
                    self.color.start()

        else:
            return

# 测试用主函数
if __name__ == '__main__':
    app = QApplication(sys.argv)
    GoBang = cBoard_Ui()
    GoBang.show()
    sys.exit(app.exec_())