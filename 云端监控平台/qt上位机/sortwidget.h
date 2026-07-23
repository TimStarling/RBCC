#ifndef SORTWIDGET_H
#define SORTWIDGET_H

#include "abstuctwidget.h"
#include "Http.h"
#include "Image.h"
#include <QCamera>
#include <QCameraImageCapture>
#include <QCameraInfo>
#include <QCameraViewfinder>
#include <QLabel>


namespace Ui {
class SortWidget;
}

class SortWidget : public AbstuctWidget
{
    Q_OBJECT

public:
    explicit SortWidget(QWidget *parent = nullptr);
    ~SortWidget();
    void closeCamera();

signals:
    void signalSendTcpMessage(const QString &message);

private slots:
    void on_pushButton_clicked();

    void on_pushButton_return_clicked();

    void on_pushbutton_open_clicked();

    void on_pushButton_close_clicked();

    void on_pushButton_sort_pressed();

    void on_pushButton_sort_released();

    void onImageSaved(int id, const QString &fileName);

    void onImageCaptureError(int id, QCameraImageCapture::Error error, const QString &errorString);

private:
    Ui::SortWidget *ui;

    QCamera *camera;
    QList<QCameraInfo> cameraInfoList;
    QCameraViewfinder *viewfinder;
    QCameraImageCapture *cameraImg;
    QLabel *cameraClosedImage;
    QString imgPath;
    QString baiduAccessToken;
    bool recognizeAfterSave;

    void updateCameraButtonState(bool opened);
    void releaseCamera();
    void setResultText(const QString &text);
    bool ensureBaiduAccessToken();
    QString requestSortResult(const QString &fileName);
    void recognizeSavedImage();



};

#endif // SORTWIDGET_H
