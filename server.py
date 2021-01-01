import socket
import socketserver
from socketserver import DatagramRequestHandler as drh
import threading
import sys
import time
import queue
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from game import game


# 存储结构
# id为int类型
id_usr = {}  # 用户id->用户名
usr_rcv = {}  # 用户id->(ip, 端口号)
id_game = {}  # 用户id->(棋局名，棋子颜色)
game_list = {}  # 棋局名->棋局
id_score = {}   # 积分榜,id->score
game_itemrow = {}   # 游戏名和item元素行对应，方便查找
id_itemrow = {}     # 用户id和item元素行对应
# 状态数据
login_usr = 0  # 当前登录的用户人数
nxt_id = 0  # 下一个分配的id号

# 互斥锁
signal_lock = threading.Lock()    # 锁信号量
var_lock = threading.Lock()       # 锁全局变量
# 数据队列，存放变更信息
pq = queue.Queue()      # 用户信息变更，存用户id
gq = queue.Queue()      # 游戏信息变更，存游戏名gn
bq = queue.Queue()      # 棋盘信息变更，存走棋(gn,x,y,color),后三者全为-1表示重开游戏


# 服务器发消息线程
class serSND():
    def __init__(self):
        self.host = socket.gethostname()
        # 获取本机ip
        self.ip = socket.gethostbyname(self.host)
        print(self.ip)
        self.buf_size = 1024
        self.send_port = 7777
        self.send_addr = (self.ip, self.send_port)
        self.server_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # 服务器主动发消息
    def send(self, name, msg):
        id = int(name)
        usr_addr = usr_rcv[id]
        self.server_send.sendto(msg.encode('utf-8'), usr_addr)

    # 发消息指令
    def msg(self, name, content):
        id = int(name)
        # content = input('请输入你要发的消息')  # 暂定发送输入的消息
        self.send(id, '~m~'+content)

    # 游戏开始通知
    def play(self, name):
        self.send(int(name), '~p')

    # 踢人, 将清空整个棋局，并通知对战双方
    def kickout(self, name):
        id = int(name)
        game_name = id_game[id][0]
        game = game_list[game_name]
        oppo = game.get_oppo(id)
        # 从玩家对战情况中删除被踢玩家和其对手，并通知他们
        id_game.pop(oppo)
        id_game.pop(id)
        self.send(id, "~k")                                                      # kicked 你已被踢出棋局
        self.send(oppo, "~o")                                                    # opponent kicked 你的对手已被踢出棋局，所以你也不能玩咯
        # 获取互斥锁
        if var_lock.acquire():
            game_list[game_name].kick()                                     # game类的kick函数
            var_lock.release()
        # 更新用户和游戏消息队列
        if signal_lock.acquire():
            gq.put(game_name)                                                   # 游戏信息更新加入消息队列
            pq.put(id)                                                          # 双方用户信息更新加入消息队列
            pq.put(oppo)
            signal_lock.release()

    # 输入棋局名开新局
    def opengame(self, game_name):
        new = game(game_name)
        if new in game_list:
            return "~e"                                 # exist: 已经有这个棋局名了，重新写一个叭
        # 获取互斥锁
        if var_lock.acquire():
            game_list[game_name] = new
            var_lock.release()
        if signal_lock.acquire():
            gq.put(game_name)
            signal_lock.release()
        return "~n~" + game_name                        # new: 新增棋局：

    # 输入棋局名关闭棋局
    def closegame(self, game_name):
        if game_name not in game_list:
            return "~c"                                 # 还没有这个棋局，你输错了叭
        game = game_list[game_name]
        id1 = game.usr1
        id2 = game.usr2
        # 如果有人在棋局中，找到棋局中的玩家，从对战情况中删除并通知他们
        # 获取互斥锁
        if var_lock.acquire():
            game_list.pop(game_name)
            if id1 != -1:
                id_game.pop(id1)
                self.send(id1, "~c")            # 你的棋局被关掉了！
            if id2 != -1:
                id_game.pop(id2)
                self.send(id2, "~c")
            var_lock.release()
        if signal_lock.acquire():
            gq.put(game_name)                   # 关闭棋局信息加入队列
            if id1 != -1:
                pq.put(id1)                     # 玩家信息更改加入队列
            if id2 != -1:
                pq.put(id2)
            signal_lock.release()

    # 关闭socket
    def close_socket(self):
        self.server_send.close()


# 全局发消息类
server_send = serSND()


# 服务器通讯线程
class server_rcv_thread(QThread):
    def __init__(self):
        super(QThread, self).__init__()
        # server
        self.host = socket.gethostname()
        ip = socket.gethostbyname(self.host)
        print("rcv ip:",ip)
        self.rcv_port = 8888
        self.rcv_addr = (ip, self.rcv_port)
        self.server_rcv = socketserver.UDPServer(self.rcv_addr, serUDP)

    def run(self):
        self.server_rcv.serve_forever()


# 作为服务器接收客户端消息并应答
class serUDP(drh):
    def handle(self):
        # print('client\'s address: ', self.client_address)
        global login_usr, nxt_id
        # 接受客户端消息
        msg = self.rfile.readline()
        # 若消息有误，在服务器打印错误信息
        if not msg:
            print("null msg from player")
        msg = msg.decode('utf-8')
        data = msg.split('-')

        # 对首次登陆的用户(发来信息"player_name-rcv_port")
        if msg[0] != '-':
            # 确认该玩家是否已经登陆过，若有则发回原有id
            exist = False
            for i in id_usr:
                if usr_rcv[i] == (self.client_address[0], int(data[1])):
                    self.wfile.write(str(i).encode('utf-8'))  # 把分配好的id发给用户
                    print('Exist. The addr send is: ', data[1])
                    exist = True
            if not exist:
                # 获取互斥锁
                if var_lock.acquire():
                    new_id = nxt_id
                    nxt_id += 1
                    login_usr += 1
                    id_usr[new_id] = data[0]
                    usr_rcv[new_id] = (self.client_address[0], int(data[1]))  # 记录用户发来的固定接收端口号
                    id_score[new_id] = 0                                      # 新用户积分初始化为0
                    var_lock.release()
                if signal_lock.acquire():
                    pq.put(new_id)
                    signal_lock.release()
                # ip_usr[self.client_address[0]] = new_id
                i = str(new_id)
                self.wfile.write(i.encode('utf-8'))                           # 把分配好的id发给用户
                print('The id send is: ' + i)                                 # 测试用

        # 对已有id用户(信息首段为"-"+自己的id)
        else:
            print('I rcv:' + msg)
            s = ''                              # 测试用
            id = int(data[1])                            # 为方便以后在其他字典中查找，这里统一改为int
            op = data[2]                                 # 分割后data第一个项为空，避开
            # 对发出棋局名的用户(发来信息"-id-g-gamename")
            if op == 'g':
                game_name = data[3]
                # 确保有此游戏
                if data[3] in game_list:
                    state = game_list[game_name].state()
                    msg = ""
                    # 如果当前棋局还没有玩家
                    if state == 0:
                        # 获取互斥锁
                        if var_lock.acquire():
                            game_list[game_name].add(id)
                            id_game[id] = game_name, 0
                            var_lock.release()
                        if signal_lock.acquire():
                            gq.put(game_name)                       # 游戏名加入消息队列
                            pq.put(id)
                            signal_lock.release()
                        msg = "0"                                   # 分发白棋
                    # 只有1个玩家
                    elif state == 1:
                        # 获取互斥锁
                        if var_lock.acquire():
                            game_list[game_name].add(id)
                            id_game[id] = game_name, 1
                            # 通知对方玩家开始游戏
                            oppo = game_list[game_name].usr1
                            server_send.play(oppo)
                            var_lock.release()
                        if signal_lock.acquire():
                            gq.put(game_name)  # 游戏名加入消息队列
                            pq.put(id)
                            pq.put(oppo)
                            signal_lock.release()
                        msg = "1"
                        # 开始棋局。待写
                    else:
                        msg = "-1"                          # you've choose a full game.
                else:
                    msg = "-2"                              # 没有这样的游戏
                self.wfile.write(msg.encode('utf-8'))       # 加入信息写给用户

            # 需要查找对手地址的操作
            elif op == 'm' or op == 'r' or op == 'l' or op == 'w':
                game_id = id_game[id][0]
                game = game_list[game_id]
                # 查找对手的id和棋子颜色
                oppo = game.get_oppo(id)
                # 边界处理：如果当前棋局中只有一个玩家
                if oppo == -1:
                    if op == 'l':
                        # 获取互斥锁
                        if var_lock.acquire():
                            id_game.pop(id)
                            game.kick()
                            var_lock.release()
                        if signal_lock.acquire():
                            gq.put(game.name)            # 游戏更新加入消息队列
                            pq.put(id)                   # 用户状态更新加入消息队列
                            signal_lock.release()
                    else:
                        self.wfile.write("n".encode('utf-8'))                           # 未开始棋局不能重开或走棋或悔棋
                # 正常双人对战
                else:
                    # 客户端要求悔棋("-id-r")
                    if op == 'r':
                        server_send.send(oppo, msg)                                         # 把当前消息转发给对手
                    # 客户端走棋(信息"-id-m-x-y")
                    if op == 'm':
                        color = game.get_color(id)                               # 获取本次走棋者棋子颜色
                        if color == game.board.last_draw:                         # 如果连走两次棋
                            self.wfile.write("d".encode('utf-8'))
                        else:
                            x = int(data[3])
                            y = int(data[4])
                            result = game.board.move(x, y, color)                # 更新自己的棋盘
                            # 错误落子位置
                            if result < 0:
                                self.wfile.write("w".encode('utf-8'))
                            else:
                                server_send.send(oppo, msg)                             # 把当前消息转发给对手
                                # 获取互斥锁
                                if signal_lock.acquire():
                                    bq.put((game_id, x, y, color))                            # 棋盘更新加入消息队列
                                    signal_lock.release()
                                # 如果分出胜负，向双方发消息表明胜负已分，更新积分榜，等待用户自己退出游戏
                                if result == 1:
                                    self.wfile.write("v".encode('utf-8'))
                                    print('Game over, this guy had won')                                # 测试用
                                    server_send.send(oppo, "~l")       # 向对手发送他输了的消息
                                    # 获取互斥锁
                                    if var_lock.acquire():
                                        id_score[id] += 1                                   # 更新积分
                                        var_lock.release()
                                    if signal_lock.acquire():
                                        pq.put(id)                                          # 用户信息更新加入消息队列
                                        signal_lock.release()
                    # 用户退出(信息"-id-l")
                    if op == 'l':
                        server_send.send(oppo, msg)              # 把当前消息转发给对手
                        # 获取互斥锁
                        if var_lock.acquire():
                            id_game.pop(id)
                            id_game.pop(oppo)
                            game_list[game_id].kick()       # 单方退出直接清空游戏
                            var_lock.release()
                        if signal_lock.acquire():
                            gq.put(game_id)                 # 游戏变更加入消息队列
                            pq.put(id)                      # 用户信息更新加入消息队列
                            pq.put(oppo)                    # 对手用户信息更新加入消息队列      ?
                            signal_lock.release()

                    # 用户悔棋(信息"-id-w-x-y")
                    if op == 'w':
                        # 对方还未走棋，可以悔棋
                        if game.get_color(id) == game.board.last_draw:
                            x = int(data[3])
                            y = int(data[4])
                            server_send.send(oppo, msg)                                         # 把当前消息转发给对手
                            # 获取互斥锁
                            if var_lock.acquire():
                                game.board.withdraw(x, y)
                                var_lock.release()
                            if signal_lock.acquire():
                                bq.put((game_id, x, y, -1))                               # 悔棋信息加入消息队列，对应棋盘颜色变-1
                                signal_lock.release()
                        else:
                            self.wfile.write('n'.encode('utf-8'))

                # 回复客户端以让其能关闭临时端口
                self.wfile.write("y".encode('utf-8'))
                print('the operation is: ' + op)

            # 同意/不同意重开游戏(信息"-id-y/n-oid")
            elif op == 'y' or op == 'n':
                game_id = id_game[id][0]
                game = game_list[game_id]
                oppo = int(data[3])
                if op == 'y':
                    # 获取互斥锁
                    if var_lock.acquire():
                        game.clear_board()
                        var_lock.release()
                    rply = "c"
                    self.wfile.write(rply.encode('utf-8'))
                else:
                    rply = "n"
                    self.wfile.write("y".encode('utf-8'))
                server_send.send(oppo, rply)
                print('restart call reply: ' + op)

            # 玩家请求当前正在比赛的棋局(会发送所有棋局)
            # 格式：游戏名，用户1，用户2
            # 不同游戏之间以'.'分割
            elif op == 'lg':
                lg = ""
                # 获取互斥锁
                if var_lock.acquire():
                    for i in game_list:
                        if game_list[i].state() == 2:
                            s = str(i) + ',' + id_usr[game_list[i].usr1] + ',' + id_usr[game_list[i].usr2] + '.'
                        elif game_list[i].state() == 1:
                            s = str(i) + ',' + id_usr[game_list[i].usr1] + ',None.'
                        elif game_list[i].state() == 0:
                            s = str(i) + ',None,None.'
                        lg += s
                    var_lock.release()
                if lg == "":
                    lg = "."
                self.wfile.write(lg.encode('utf-8'))

            # 玩家请求服务器的当前所有玩家列表，及其参加棋局的情况
            # 格式：用户名，用户积分，用户所在棋局
            # 用'.'分割，如果没有发送'.'
            elif op == 'lu':
                lu = ""
                # 获取互斥锁
                if var_lock.acquire():
                    for i in id_usr:
                        # 判断用户是否有加入游戏
                        if i in id_game:
                            s = id_usr[i] + ',' + str(id_score[i]) + ',' + id_game[i][0] + '.'
                        else:
                            s = id_usr[i] + ',' + str(id_score[i]) + ',' + 'None' + '.'
                        lu += s
                    var_lock.release()
                self.wfile.write(lu.encode('utf-8'))
                if lu == "":
                    lu = "."
            elif not s:
                print(s)                            # 测试，错误处理


# 通讯中产生变化的消息队列处理
class signalhandle(QThread):
    PlayerSignal = pyqtSignal(int)              # 玩家编号，通知玩家变更
    GameSignal = pyqtSignal(str)                # 游戏名，通知游戏变更
    boardSignal = pyqtSignal(str, int, int, int)               # 游戏名，落子点，棋子色,通知棋盘变化

    def run(self):
        while True:
            time.sleep(1)
            if signal_lock.acquire():
                while not pq.empty():
                    s = pq.get()
                    self.PlayerSignal.emit(s)
                while not gq.empty():
                    s = gq.get()
                    self.GameSignal.emit(s)
                while not bq.empty():
                    s = bq.get()
                    self.boardSignal.emit(s[0],s[1],s[2],s[3])
                signal_lock.release()


# u1, u2为用户名字符串
class Board_Ui(QWidget):
    def __init__(self, g, u1, u2):
        super().__init__()
        self.setupUi(g, u1, u2)

    # 静态GUI设置, g为game类
    def setupUi(self, g, u1, u2):
        self.num = 0                                      # 棋盘中已画出的棋子数
        self.u1 = u1
        self.u2 = u2
        self.g = g
        self.setObjectName("Board")
        self.resize(710, 640)
        self.setWindowIcon(QIcon("./board.bmp"))
        self.label = QLabel(self)
        self.label.setGeometry(QRect(10, 80, 550, 550))
        self.label.setText("")
        self.label.setPixmap(QPixmap("./board.bmp"))
        self.label.setScaledContents(True)
        self.label.setObjectName("label")
        self.Monitor = QLabel(self)
        self.Monitor.setGeometry(QRect(210, 15, 300, 50))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(20)
        font.setBold(False)
        font.setWeight(50)
        self.Monitor.setFont(font)
        self.Monitor.setObjectName("Monitor")
        self.Black = QLabel(self)
        self.Black.setGeometry(QRect(590, 200, 100, 20))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(12)
        font.setBold(True)
        font.setWeight(75)
        self.Black.setFont(font)
        self.Black.setObjectName("Black")
        self.White = QLabel(self)
        self.White.setGeometry(QRect(590, 120, 100, 20))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(12)
        font.setBold(True)
        font.setWeight(75)
        self.White.setFont(font)
        self.White.setObjectName("White")
        self.kick = QPushButton(self)
        self.kick.setGeometry(QRect(585, 525, 90, 35))

        # 设置按键等
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(10)
        self.kick.setFont(font)
        self.kick.setObjectName("kick")
        self.leave = QPushButton(self)
        self.leave.setGeometry(QRect(585, 570, 90, 35))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(10)
        self.leave.setFont(font)
        self.leave.setObjectName("leave")
        self.b_name = QLabel(self)
        self.b_name.setGeometry(QRect(590, 230, 150, 25))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(10)
        font.setBold(False)
        self.b_name.setFont(font)
        self.b_name.setObjectName("b_name")
        self.w_name = QLabel(self)
        self.w_name.setGeometry(QRect(590, 150, 150, 25))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(10)
        font.setBold(False)
        self.w_name.setFont(font)
        self.w_name.setObjectName("w_name")
        # 设置文字
        self.setWindowTitle(g.name)                            # 窗体名设为游戏名
        self.Monitor.setText("Monitor")
        self.Black.setText("Black")
        self.White.setText("White")
        self.kick.setText("Kick")
        self.leave.setText("Leave")
        self.b_name.setText(u1)
        self.w_name.setText(u2)
        QMetaObject.connectSlotsByName(self)
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

        # 画出已经有棋子的点
        for i in range(15):
            for j in range(15):
                if g.board.board[i][j] != -1:
                    self.paint(g.name, i, j, g.board.board[i][j])
        # 连接信号和槽函数
        self.kick.clicked.connect(self.kick_usr)
        self.leave.clicked.connect(self.leave_watch)

    # 槽函数
    # 踢玩家
    def kick_usr(self):
        ok = QMessageBox.question(self, 'Kick', "Do you want to kick " + self.u1 + "?",
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ok == QMessageBox.Yes:
            server_send.kickout(self.g.usr1)
        else:
            ok = QMessageBox.question(self, 'Kick', "Do you want to kick " + self.u2 + "?",
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ok == QMessageBox.Yes:
                server_send.kickout(self.g.usr2)

    # 退出提醒,点确认关闭窗体
    def leave_watch(self):
        ok = QMessageBox.question(self, 'Leave', "Do you want to leave the watch?",
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ok == QMessageBox.Yes:
            self.close()

    # 棋盘逻辑-物理转换函数, x16-520 y84-588 step36
    def logal2pixel(self, x, y):
        # 检查输入合法
        if x in range(0, 14) and y in range(0, 14):
            return x * 36 + 16, y * 36 + 84
        return None, None
    
    # 绘制棋盘, 这里只需接受逻辑坐标
    # 接受棋盘变动信号量的参数：游戏名game，落子点逻辑坐标x, y, color,
    def paint(self, game, lx, ly, color):
        # 由于所有棋盘动态都会引发信号，只对当前观战棋盘信号做响应
        if game == self.g.name:
            x, y = self.logal2pixel(lx, ly)
            # 检查坐标合法性
            if not x or not y:
                return
            # 修改棋子列表中的下一个未赋值label，根据颜色选择绘制
            piece = self.pieces[self.num]
            if color == 0:
                piece.setPixmap(self.pieceW)
            else:
                piece.setPixmap(self.pieceB)
            piece.setGeometry(QRect(x, y, 35, 35))
            self.num += 1


# 主界面
class Bang_Ui(QWidget):
    def __init__(self):
        super().__init__()
        self.server = server_rcv_thread()               # 启动服务器收消息线程
        self.server.start()
        self.signal_h = signalhandle()                  # 信号量
        self.signal_h.start()
        self.setupUi()                                  # 初始化界面

    # 静态GUI设置
    def setupUi(self):
        self.setObjectName("GoBang")
        self.resize(600, 700)
        sizePolicy = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sizePolicy)
        self.setWindowTitle("Gobang Monitor")
        self.setWindowIcon(QIcon("./board.bmp"))
        self.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        self.gamel = QLabel(self)
        self.gamel.setGeometry(QRect(40, 40, 150, 40))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(14)
        font.setBold(True)
        font.setWeight(75)
        self.gamel.setFont(font)
        self.gamel.setObjectName("gamel")
        self.userl = QLabel(self)
        self.userl.setGeometry(QRect(40, 370, 150, 40))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(14)
        font.setBold(True)
        font.setWeight(75)
        self.userl.setFont(font)
        self.userl.setObjectName("userl")

        # 设置按钮等
        self.gamelist = QTableView(self)
        self.gamelist.setGeometry(QRect(40, 90, 520, 250))
        self.gamelist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.gamelist.setObjectName("gamelist")
        self.gamelist.model = QStandardItemModel()
        self.gamelist.model.setHorizontalHeaderLabels(['Game', 'White', 'Black'])
        self.gamelist.setModel(self.gamelist.model)
        self.gamelist.horizontalHeader().setStretchLastSection(True)
        self.gamelist.setSelectionBehavior(QAbstractItemView.SelectRows)  # 设置整行选中
        self.userlist = QTableView(self)
        self.userlist.setGeometry(QRect(40, 420, 520, 250))
        self.userlist.setObjectName("userlist")
        self.userlist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.userlist.model = QStandardItemModel()
        self.userlist.model.setHorizontalHeaderLabels(['User Name', 'User ID', 'Game'])
        self.userlist.setModel(self.userlist.model)
        self.userlist.horizontalHeader().setStretchLastSection(True)
        # self.userlist.horizontalHeader().SetSectionResizeMode(QHeaderView.Stretch)  #设置表格填满窗口
        self.userlist.setSelectionBehavior(QAbstractItemView.SelectRows)        #设置整行选中
        # 设置按钮
        self.msg = QPushButton(self)
        self.msg.setGeometry(QRect(460, 370, 100, 40))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(11)
        self.msg.setFont(font)
        self.msg.setObjectName("msg")
        self.open = QPushButton(self)
        self.open.setGeometry(QRect(480, 40, 80, 40))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(11)
        self.open.setFont(font)
        self.open.setObjectName("open")
        self.close = QPushButton(self)
        self.close.setGeometry(QRect(390, 40, 80, 40))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(11)
        self.close.setFont(font)
        self.close.setObjectName("close")
        self.watch = QPushButton(self)
        self.watch.setGeometry(QRect(300, 40, 80, 40))
        font = QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(11)
        self.watch.setFont(font)
        self.watch.setObjectName("watch")

        # 设置文字
        self.gamel.setText("Game List")
        self.userl.setText("User List")
        self.msg.setText("Message")
        self.open.setText("Open")
        self.close.setText("Close")
        self.watch.setText("Watch")

        # 初始化已有的用户和游戏列表
        for i in id_game:
            self.fill_usr(i)
        for j in game_list:
            self.fill_game(j)

        # 信号连接槽函数
        self.open.clicked.connect(self.open_game)
        self.close.clicked.connect(self.close_game)
        self.watch.clicked.connect(self.watch_game)
        self.msg.clicked.connect(self.msg_usr)
        self.signal_h.PlayerSignal.connect(self.fill_usr)
        self.signal_h.GameSignal.connect(self.fill_game)
        QMetaObject.connectSlotsByName(self)


    # 槽函数
    # 新建游戏
    def open_game(self):
        dialog = QInputDialog()
        dialog.resize(400, 300)
        text, ok = dialog.getText(self, "Open a Game", "Game name:", QLineEdit.Normal, "")
        if ok and text != '':
            server_send.opengame(text)

    # 关闭游戏
    def close_game(self):
        g = self.gamelist.selectedIndexes()
        if g:
            buttonReply = QMessageBox.question(self, 'Warning', "Do you want to cancel this?",
                                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if buttonReply == QMessageBox.Yes:
                for i in range(0, len(g), 3):
                    server_send.closegame(g[i].data())
        else:
            return

    # 观看游戏
    def watch_game(self):
        g = self.gamelist.selectedIndexes()
        if g:
            # 每次只能观看一个棋局
            if len(g) > 3:
                ok = QMessageBox.warning(self, 'Multi-Game', "You can only watch one game at a time",
                                          QMessageBox.Ok)
                if ok == QMessageBox.Ok:
                    return
            else:
                # 获取互斥锁
                if var_lock.acquire():
                    game = game_list[g[0].data()]
                    u1 = id_usr[game.usr1]
                    u2 = id_usr[game.usr2]
                    var_lock.release()
                self.watch_board = Board_Ui(game, u1, u2)
                self.signal_h.boardSignal.connect(self.watch_board.paint)         # 连接子窗体绘制棋盘的函数和棋子变动信号量
                self.watch_board.show()
        else:
            return

    # 发送消息
    def msg_usr(self):
        name = self.userlist.selectedIndexes()
        dialog = QInputDialog()
        dialog.resize(400, 300)
        font = QFont()
        font.setFamily("Palatino Linotype")
        dialog.setFont(font)
        content, okPressed = dialog.getText(self, "Message", "Your message:", QLineEdit.Normal, "")
        if okPressed and name:
            for i in range(1, len(name), 3):
                server_send.msg(name[i].data(), content)

    # 输出数据到用户列表, 不会删除用户
    def fill_usr(self, i):
        # 获取互斥锁
        if var_lock.acquire():
            # 新用户加入
            if i not in id_itemrow:
                row = self.userlist.model.rowCount()
                id_itemrow[i] = row
            else:
                row = id_itemrow[i]
            item1 = QStandardItem(id_usr[i])
            # 如果玩家已经加入游戏就获取游戏名，否则为空值
            if i in id_game:
                item2 = QStandardItem(id_game[i][0])
            else:
                item2 = QStandardItem("None")
            var_lock.release()
        item3 = QStandardItem(str(i))
        self.userlist.model.setItem(row, 0, item1)
        self.userlist.model.setItem(row, 1, item3)
        self.userlist.model.setItem(row, 2, item2)

    # 输出数据到游戏列表
    def fill_game(self, game):
        # 获取互斥锁
        if var_lock.acquire():
            # 处理删除游戏的情况，即输入的游戏名不存在于游戏列表中,删除整列
            if game not in game_list:
                row = game_itemrow[game]
                self.gamelist.model.removeRow(row)
            # 增加或修改游戏状态
            else:
                # 增加一个新游戏
                if game not in game_itemrow:
                    row = self.gamelist.model.rowCount()
                    game_itemrow[game] = row
                # 对已有游戏的处理
                else:
                    row = game_itemrow[game]
                # 处理游戏中可能还没有玩家的情况
                if game_list[game].usr1 != -1:
                    item2 = QStandardItem(id_usr[game_list[game].usr1])
                else:
                    item2 = QStandardItem("None")
                if game_list[game].usr2 != -1:
                    item3 = QStandardItem(id_usr[game_list[game].usr2])
                else:
                    item3 = QStandardItem("None")
                item1 = QStandardItem(game)
                self.gamelist.model.setItem(row, 0, item1)
                self.gamelist.model.setItem(row, 1, item2)
                self.gamelist.model.setItem(row, 2, item3)
            var_lock.release()

    # 重载关闭关闭socket
    def closeEvent(self, a0: QCloseEvent):
        server_send.close_socket()

# 测试用主函数
if __name__ == '__main__':
    app = QApplication(sys.argv)
    goBang = Bang_Ui()
    goBang.show()
    sys.exit(app.exec_())
