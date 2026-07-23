#include "Http.h"
#include <QEventLoop>
#include <QMapIterator>

Http::Http()
{

}

bool Http::post_sync(QString url, QMap<QString, QString> header, QByteArray &requestData, QByteArray &replyData)
{
    QNetworkAccessManager manager; //发送请求的动作
    QNetworkRequest request;       //请求的内容（包含Url和头）
    request.setUrl(url);
    QMapIterator<QString, QString> it(header);
    while (it.hasNext())
    {
        it.next();
        request.setRawHeader(it.key().toLatin1(), it.value().toLatin1());
    }



    QNetworkReply *reply = manager.post(request, requestData);
    QEventLoop el;
    connect(reply, &QNetworkReply::finished, &el, &QEventLoop::quit);
    el.exec();

    if (reply != nullptr && reply->error() == QNetworkReply::NoError)
    {
        replyData = reply->readAll();
        return true;
    }
    else
        return false;
}
