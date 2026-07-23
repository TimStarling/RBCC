#include "sortwidget.h"
#include "config.h"
#include "ui_sortwidget.h"

#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QMessageBox>
#include <QStandardPaths>
#include <QStackedLayout>

namespace {
QString textWaiting()
{
    return QStringLiteral("\u7b49\u5f85\u5206\u62e3\u3002");
}

QString textNoCamera()
{
    return QStringLiteral("\u672a\u627e\u5230\u53ef\u7528\u6444\u50cf\u5934\u3002");
}

QString textCamera()
{
    return QStringLiteral("\u6444\u50cf\u5934");
}

QString textCameraOpened()
{
    return QStringLiteral("\u6444\u50cf\u5934\u5df2\u6253\u5f00\uff0c\u53ef\u4ee5\u5f00\u59cb\u5206\u62e3\u3002");
}

QString textCameraClosed()
{
    return QStringLiteral("\u6444\u50cf\u5934\u5df2\u5173\u95ed\u3002");
}

QString textSort()
{
    return QStringLiteral("\u5206\u62e3");
}

QString textOpenCameraFirst()
{
    return QStringLiteral("\u8bf7\u5148\u6253\u5f00\u6444\u50cf\u5934\u3002");
}

QString textCameraNotReady()
{
    return QStringLiteral("\u6444\u50cf\u5934\u5c1a\u672a\u51c6\u5907\u597d\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002");
}

QString textSavingAndRecognizing()
{
    return QStringLiteral("\u6b63\u5728\u4fdd\u5b58\u56fe\u7247\u5e76\u8bc6\u522b...");
}

QString textCaptureFailed()
{
    return QStringLiteral("\u62cd\u7167\u5931\u8d25\uff1a");
}

QString textTokenFailed()
{
    return QStringLiteral("\u83b7\u53d6\u8bc6\u522b\u6a21\u578b\u8bbf\u95ee\u4ee4\u724c\u5931\u8d25\u3002");
}

QString textUnknownGoods()
{
    return QStringLiteral("\u672a\u77e5\u5546\u54c1\uff0c\u8bf7\u91cd\u65b0\u5206\u62e3\uff01");
}
}

SortWidget::SortWidget(QWidget *parent) :
    AbstuctWidget(parent),
    ui(new Ui::SortWidget),
    camera(nullptr),
    cameraInfoList(QCameraInfo::availableCameras()),
    viewfinder(nullptr),
    cameraImg(nullptr),
    cameraClosedImage(nullptr),
    baiduAccessToken(),
    recognizeAfterSave(false)
{
    ui->setupUi(this);

    QWidget *cameraViewContainer = new QWidget(this);
    cameraViewContainer->setGeometry(60, 90, 471, 430);

    QStackedLayout *cameraLayout = new QStackedLayout(cameraViewContainer);
    cameraLayout->setContentsMargins(0, 0, 0, 0);
    cameraLayout->setSpacing(0);
    cameraLayout->setStackingMode(QStackedLayout::StackAll);

    viewfinder = new QCameraViewfinder(cameraViewContainer);

    cameraClosedImage = new QLabel(cameraViewContainer);
    cameraClosedImage->setPixmap(QPixmap(":/image/camera_closed.jpg"));
    cameraClosedImage->setScaledContents(true);

    cameraLayout->addWidget(viewfinder);
    cameraLayout->addWidget(cameraClosedImage);
    cameraClosedImage->raise();

    setResultText(textWaiting());
    updateCameraButtonState(false);
}

SortWidget::~SortWidget()
{
    releaseCamera();
    delete ui;
}

void SortWidget::on_pushButton_clicked()
{
    signalJumpWidget(AD_WIDGET);
}

void SortWidget::on_pushButton_return_clicked()
{
    signalJumpWidget(TCP_WIDGET);
}

void SortWidget::on_pushbutton_open_clicked()
{
    if (camera != nullptr && camera->state() == QCamera::ActiveState) {
        return;
    }

    if (camera != nullptr) {
        releaseCamera();
    }

    cameraInfoList = QCameraInfo::availableCameras();
    if (cameraInfoList.isEmpty()) {
        setResultText(textNoCamera());
        QMessageBox::warning(this, textCamera(), textNoCamera());
        updateCameraButtonState(false);
        return;
    }

    if (camera == nullptr) {
        camera = new QCamera(cameraInfoList.at(0), this);
        camera->setViewfinder(viewfinder);

        cameraImg = new QCameraImageCapture(camera, this);
        connect(cameraImg, &QCameraImageCapture::imageSaved,
                this, &SortWidget::onImageSaved);
        connect(cameraImg, QOverload<int, QCameraImageCapture::Error, const QString &>::of(&QCameraImageCapture::error),
                this, &SortWidget::onImageCaptureError);
    }

    camera->start();
    setResultText(textCameraOpened());
    updateCameraButtonState(true);
}

void SortWidget::on_pushButton_close_clicked()
{
    closeCamera();
}

void SortWidget::on_pushButton_sort_pressed()
{
    if (camera == nullptr || camera->state() != QCamera::ActiveState || cameraImg == nullptr) {
        setResultText(textOpenCameraFirst());
        QMessageBox::warning(this, textSort(), textOpenCameraFirst());
        return;
    }

    if (!cameraImg->isReadyForCapture()) {
        setResultText(textCameraNotReady());
        QMessageBox::warning(this, textSort(), textCameraNotReady());
        return;
    }

    const QString captureDir = QStandardPaths::writableLocation(QStandardPaths::PicturesLocation)
            + "/SmartSort";
    QDir().mkpath(captureDir);

    const QString time = QDateTime::currentDateTime().toString("yyyy-MM-dd-hh-mm-ss");
    imgPath = captureDir + QString("/%1.jpg").arg(time);

    recognizeAfterSave = false;
    setResultText(textSavingAndRecognizing());
    camera->searchAndLock();
    cameraImg->capture(imgPath);
}

void SortWidget::on_pushButton_sort_released()
{
    if (imgPath.isEmpty()) {
        return;
    }

    if (QFileInfo::exists(imgPath)) {
        recognizeSavedImage();
        return;
    }

    recognizeAfterSave = true;
}

void SortWidget::onImageSaved(int id, const QString &fileName)
{
    Q_UNUSED(id)

    imgPath = fileName;
    if (camera != nullptr) {
        camera->unlock();
    }

    if (recognizeAfterSave) {
        recognizeSavedImage();
    }
}

void SortWidget::onImageCaptureError(int id, QCameraImageCapture::Error error, const QString &errorString)
{
    Q_UNUSED(id)
    Q_UNUSED(error)

    recognizeAfterSave = false;
    if (camera != nullptr) {
        camera->unlock();
    }
    setResultText(textCaptureFailed() + errorString);
}

void SortWidget::updateCameraButtonState(bool opened)
{
    ui->pushbutton_open->setEnabled(!opened);
    ui->pushButton_close->setEnabled(opened);

    viewfinder->setVisible(opened);
    cameraClosedImage->setVisible(!opened);
    if (!opened) {
        cameraClosedImage->raise();
    }
}

void SortWidget::closeCamera()
{
    releaseCamera();
    setResultText(textCameraClosed());
    updateCameraButtonState(false);
}

void SortWidget::releaseCamera()
{
    recognizeAfterSave = false;

    if (camera != nullptr) {
        camera->unlock();
        camera->stop();
        camera->setViewfinder(static_cast<QCameraViewfinder *>(nullptr));
    }

    delete cameraImg;
    cameraImg = nullptr;

    delete camera;
    camera = nullptr;
}

void SortWidget::setResultText(const QString &text)
{
    ui->textEdit_result->setPlainText(text);
}

void SortWidget::recognizeSavedImage()
{
    recognizeAfterSave = false;
    const QString goodsName = requestSortResult(imgPath);
    setResultText(goodsName);

    if (goodsName.trimmed() == QStringLiteral("\u624b\u8868")) {
        emit signalSendTcpMessage(QStringLiteral("1"));
    }
}

bool SortWidget::ensureBaiduAccessToken()
{
    if (!baiduAccessToken.isEmpty()) {
        return true;
    }

    QByteArray replyData;
    QString url = QString(baiduToken).arg(client_id).arg(secret_id);
    QMap<QString, QString> header;
    header.insert(QString("Content-Type"), QString("application/x-www-form-urlencoded"));

    QByteArray requestData;
    if (!Http::post_sync(url, header, requestData, replyData)) {
        return false;
    }

    QJsonObject obj = QJsonDocument::fromJson(replyData).object();
    baiduAccessToken = obj.value("access_token").toString();
    return !baiduAccessToken.isEmpty();
}

QString SortWidget::requestSortResult(const QString &fileName)
{
    if (!ensureBaiduAccessToken()) {
        return textTokenFailed();
    }

    QByteArray img = Image::imageToBase64(fileName);
    QByteArray imgData = "image=" + img;
    QByteArray replyData;
    QMap<QString, QString> header;
    header.insert(QString("Content-Type"), QString("application/x-www-form-urlencoded"));

    QString imgUrl = QString(baiduImageUrl).arg(baiduAccessToken);
    bool result = Http::post_sync(imgUrl, header, imgData, replyData);
    if (result) {
        QJsonObject obj = QJsonDocument::fromJson(replyData).object();
        const int errorCode = obj.value("error_code").toInt(0);
        const QString errorMessage = obj.value("error_msg").toString();
        if (errorCode != 0 || !errorMessage.isEmpty()) {
            if (errorCode == 18) {
                return QStringLiteral("\u8bc6\u522b\u63a5\u53e3\u8bf7\u6c42\u8fc7\u4e8e\u9891\u7e41\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002");
            }
            return QStringLiteral("\u8bc6\u522b\u5931\u8d25\uff1a") + errorMessage;
        }

        QJsonValue value = obj.value("result");
        if (value.isArray() && !value.toArray().isEmpty()) {
            QJsonValue first = value.toArray().at(0);
            if (first.isObject()) {
                QString goodsName = first.toObject().value("keyword").toString();
                if (!goodsName.isEmpty()) {
                    return goodsName;
                }
            }
        }
    }

    return textUnknownGoods();
}
