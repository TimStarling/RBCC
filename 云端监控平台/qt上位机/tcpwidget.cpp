#include "tcpwidget.h"
#include "ui_tcpwidget.h"
#include <QNetworkProxy>

namespace {
QString zh(const char *text)
{
    return QString::fromUtf8(text);
}
}

TcpWidget::TcpWidget(QWidget *parent) :
    AbstuctWidget(parent),
    ui(new Ui::TcpWidget),
    m_socket(new QTcpSocket(this)),
    m_jumpTimer(new QTimer(this)),
    m_countdownSeconds(0)
{
    ui->setupUi(this);

    m_socket->setProxy(QNetworkProxy::NoProxy);

    ui->lineEdit_IP->setText("192.168.138.131");
    ui->lineEdit_2_PORT->setText("8888");
    ui->lineEdit_3_info->setEnabled(false);
    ui->pushButton_2_send->setEnabled(false);

    connect(m_socket, &QTcpSocket::connected,
            this, &TcpWidget::onSocketConnected);
    connect(m_socket, &QTcpSocket::disconnected,
            this, &TcpWidget::onSocketDisconnected);
    connect(m_socket, &QTcpSocket::readyRead,
            this, &TcpWidget::onSocketReadyRead);
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
    connect(m_socket, &QTcpSocket::errorOccurred,
            this, &TcpWidget::onSocketError);
#else
    connect(m_socket, QOverload<QAbstractSocket::SocketError>::of(&QTcpSocket::error),
            this, &TcpWidget::onSocketError);
#endif
    connect(m_jumpTimer, &QTimer::timeout,
            this, &TcpWidget::updateJumpCountdown);
    connect(ui->lineEdit_3_info, &QLineEdit::returnPressed,
            this, &TcpWidget::on_pushButton_2_send_clicked);

    m_jumpTimer->setInterval(1000);
}

TcpWidget::~TcpWidget()
{
    delete ui;
}

bool TcpWidget::sendCommand(const QString &message)
{
    if (m_socket->state() != QAbstractSocket::ConnectedState) {
        appendMessage(zh("TCP 未连接，无法发送分拣指令。"));
        return false;
    }

    if (m_socket->write(message.toUtf8()) == -1) {
        appendMessage(zh("发送失败：") + m_socket->errorString());
        return false;
    }

    appendMessage(zh("发送分拣指令：") + message);
    return true;
}

void TcpWidget::on_pushButton_connect_clicked()
{
    if (m_socket->state() == QAbstractSocket::ConnectedState) {
        appendMessage(zh("正在断开服务器连接..."));
        ui->pushButton_connect->setEnabled(false);
        m_socket->disconnectFromHost();
        return;
    }

    if (m_socket->state() != QAbstractSocket::UnconnectedState) {
        m_socket->abort();
    }

    const QString host = ui->lineEdit_IP->text().trimmed();
    bool portOk = false;
    const quint16 port = ui->lineEdit_2_PORT->text().trimmed().toUShort(&portOk);

    if (host.isEmpty()) {
        appendMessage(zh("请输入服务器 IP 地址或主机名。"));
        ui->lineEdit_IP->setFocus();
        return;
    }

    if (!portOk || port == 0) {
        appendMessage(zh("端口无效，请输入 1-65535。"));
        ui->lineEdit_2_PORT->setFocus();
        ui->lineEdit_2_PORT->selectAll();
        return;
    }

    appendMessage(QString::fromUtf8("正在连接 %1:%2...").arg(host).arg(port));
    ui->pushButton_connect->setText(zh("连接中..."));
    ui->pushButton_connect->setEnabled(false);
    ui->lineEdit_IP->setEnabled(false);
    ui->lineEdit_2_PORT->setEnabled(false);
    m_socket->connectToHost(host, port);
}

void TcpWidget::on_pushButton_2_send_clicked()
{
    const QString message = ui->lineEdit_3_info->text().trimmed();
    if (message.isEmpty()) {
        return;
    }

    if (!sendCommand(message)) {
        return;
    }

    ui->lineEdit_3_info->clear();
    ui->lineEdit_3_info->setFocus();
}

void TcpWidget::onSocketConnected()
{
    updateConnectionUi(true);
    appendMessage(zh("已连接服务器。"));
    startJumpCountdown();
}

void TcpWidget::onSocketDisconnected()
{
    stopJumpCountdown();
    updateConnectionUi(false);
    appendMessage(zh("服务器连接已关闭。"));
}

void TcpWidget::onSocketReadyRead()
{
    const QString message = QString::fromUtf8(m_socket->readAll());
    if (!message.isEmpty()) {
        appendMessage(zh("接收：") + message);
    }
}

void TcpWidget::onSocketError(QAbstractSocket::SocketError socketError)
{
    Q_UNUSED(socketError)

    stopJumpCountdown();
    updateConnectionUi(false);
    appendMessage(zh("网络错误：") + m_socket->errorString());
}

void TcpWidget::updateJumpCountdown()
{
    --m_countdownSeconds;

    if (m_countdownSeconds > 0) {
        appendMessage(QString::fromUtf8("%1 秒后跳转到分拣页面...").arg(m_countdownSeconds));
        return;
    }

    m_jumpTimer->stop();
    appendMessage(zh("正在跳转到分拣页面..."));
    emit signalJumpWidget(SORT_WIDGET);
}

void TcpWidget::appendMessage(const QString &message)
{
    ui->textEdit->append(message.toHtmlEscaped());
}

void TcpWidget::updateConnectionUi(bool connected)
{
    ui->pushButton_connect->setEnabled(true);
    ui->pushButton_connect->setText(connected ? zh("断开连接") : zh("连接"));
    ui->lineEdit_IP->setEnabled(!connected);
    ui->lineEdit_2_PORT->setEnabled(!connected);
    ui->lineEdit_3_info->setEnabled(connected);
    ui->pushButton_2_send->setEnabled(connected);

    if (connected) {
        ui->lineEdit_3_info->setFocus();
    }
}

void TcpWidget::startJumpCountdown()
{
    m_countdownSeconds = 3;
    appendMessage(QString::fromUtf8("%1 秒后跳转到分拣页面...").arg(m_countdownSeconds));
    m_jumpTimer->start();
}

void TcpWidget::stopJumpCountdown()
{
    if (m_jumpTimer->isActive()) {
        m_jumpTimer->stop();
        m_countdownSeconds = 0;
        appendMessage(zh("已取消自动跳转。"));
    }
}
