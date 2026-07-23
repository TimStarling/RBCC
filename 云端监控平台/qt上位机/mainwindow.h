#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include "config.h"
#define MAX_PAGE 3

QT_BEGIN_NAMESPACE
namespace Ui { class MainWindow; }
QT_END_NAMESPACE

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

public slots:
    void slotJumpWedget(WidgetIndex index);

protected:
    void closeEvent(QCloseEvent *event) override;

private slots:
    void on_nextPageButton_clicked();

private:
    Ui::MainWindow *ui;
    int page;
    void closeAllCameras();
};
#endif // MAINWINDOW_H
