#ifndef TCPWIDGET_H
#define TCPWIDGET_H

#include "abstuctwidget.h"
#include <QTcpSocket>
#include <QTimer>

namespace Ui {
class TcpWidget;
}

class TcpWidget : public AbstuctWidget
{
    Q_OBJECT

public:
    explicit TcpWidget(QWidget *parent = nullptr);
    ~TcpWidget();
    bool sendCommand(const QString &message);

private slots:
    void on_pushButton_connect_clicked();
    void on_pushButton_2_send_clicked();
    void onSocketConnected();
    void onSocketDisconnected();
    void onSocketReadyRead();
    void onSocketError(QAbstractSocket::SocketError socketError);
    void updateJumpCountdown();

private:
    void appendMessage(const QString &message);
    void updateConnectionUi(bool connected);
    void startJumpCountdown();
    void stopJumpCountdown();

    Ui::TcpWidget *ui;
    QTcpSocket *m_socket;
    QTimer *m_jumpTimer;
    int m_countdownSeconds;
};

#endif // TCPWIDGET_H
