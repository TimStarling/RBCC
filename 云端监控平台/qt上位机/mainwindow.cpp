#include "mainwindow.h"
#include "sortwidget.h"
#include "tcpwidget.h"
#include "ui_mainwindow.h"
#include <QCloseEvent>
#include <QDebug>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::MainWindow)
    ,page(0)
{
    ui->setupUi(this);
    //初始化起始页
    setWindowIcon(QIcon(":/image/1.png"));
    setWindowTitle("智能分拣");
    ui->stackedWidget->setCurrentIndex(page);
    qDebug() << "总页数："<<ui->stackedWidget->count();

    //完成信号与槽函数的绑定
    for(int i=0; i<ui->stackedWidget->count();++i){
        auto widget = dynamic_cast<AbstuctWidget *>(ui->stackedWidget->widget(i));
        if(widget == nullptr) continue;
        connect(widget,
            &AbstuctWidget::signalJumpWidget,
                this,
                &MainWindow::slotJumpWedget);
    }

    TcpWidget *tcpWidget = nullptr;
    SortWidget *sortWidget = nullptr;
    for (int i = 0; i < ui->stackedWidget->count(); ++i) {
        QWidget *pageWidget = ui->stackedWidget->widget(i);
        if (tcpWidget == nullptr) {
            tcpWidget = qobject_cast<TcpWidget *>(pageWidget);
        }
        if (sortWidget == nullptr) {
            sortWidget = qobject_cast<SortWidget *>(pageWidget);
        }
    }

    if (sortWidget != nullptr && tcpWidget != nullptr) {
        connect(sortWidget, &SortWidget::signalSendTcpMessage,
                tcpWidget, &TcpWidget::sendCommand);
    }
}

MainWindow::~MainWindow()
{
    closeAllCameras();
    delete ui;
}

void MainWindow::slotJumpWedget(WidgetIndex index)
{
    page = index;
    ui->stackedWidget->setCurrentIndex(index);
}


void MainWindow::on_nextPageButton_clicked()
{
    page = (ui->stackedWidget->currentIndex() + 1) % ui->stackedWidget->count();
    ui->stackedWidget->setCurrentIndex(page);
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    closeAllCameras();
    QMainWindow::closeEvent(event);
}

void MainWindow::closeAllCameras()
{
    if (ui == nullptr) {
        return;
    }

    for (int i = 0; i < ui->stackedWidget->count(); ++i) {
        SortWidget *sortWidget = qobject_cast<SortWidget *>(ui->stackedWidget->widget(i));
        if (sortWidget != nullptr) {
            sortWidget->closeCamera();
        }
    }
}
