# -*- coding: utf-8 -*-

# self implementation generated from reading ui file 'scoreboard_u.ui'
#
# Created by: PyQt5 UI code generator 5.10.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets

class ScoreBoardUi(QtWidgets.QWidget):
    def __init__(self, usr):
        super().__init__()
        self.setupUi(usr)

    def setupUi(self, usr):
        self.setObjectName("Scoreboard")
        self.resize(560, 450)
        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(QtCore.QRect(185, 30, 200, 40))
        font = QtGui.QFont()
        font.setFamily("Palatino Linotype")
        font.setPointSize(18)
        # font.setPixelSize(25)
        font.setBold(True)
        font.setWeight(75)
        self.label.setFont(font)
        self.label.setObjectName("label")
        self.usr_score = QtWidgets.QTableView(self)
        self.usr_score.setGeometry(QtCore.QRect(30, 100, 500, 320))
        self.usr_score.setObjectName("usr_score")
        self.usr_score.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.usr_score.model = QtGui.QStandardItemModel()
        self.usr_score.model.setHorizontalHeaderLabels(['User Name', 'User Score', 'Game'])
        self.usr_score.setModel(self.usr_score.model)
        self.usr_score.horizontalHeader().setStretchLastSection(True)
        self.usr_score.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)  # 设置整行选中
        self.setWindowTitle("Score")
        self.label.setText("Scoreboard")

        # 把接收到的游戏列表切分输出到表格
        # 格式：用户名，用户积分，用户所在棋局
        splt = usr.split('.')
        row = 0
        for plr in splt:
            s = plr.split(',')
            if len(s) == 3:
                item1 = QtGui.QStandardItem(s[0])
                item2 = QtGui.QStandardItem(s[1])
                item3 = QtGui.QStandardItem(s[2])
                self.usr_score.model.setItem(row, 0, item1)
                self.usr_score.model.setItem(row, 1, item2)
                self.usr_score.model.setItem(row, 2, item3)
                row += 1
        QtCore.QMetaObject.connectSlotsByName(self)

