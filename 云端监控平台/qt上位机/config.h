#ifndef CONFIG_H
#define CONFIG_H
#include <QObject>
//对应功能页面编号
enum WidgetIndex
{
    AD_WIDGET = 0,
    TCP_WIDGET,
    SORT_WIDGET
};

// Configure local Baidu AI credentials before enabling cloud image analysis.
// Never commit real API credentials to the repository.
const QString client_id = "YOUR_BAIDU_API_KEY";
const QString secret_id = "YOUR_BAIDU_SECRET_KEY";

const QString baiduToken = "https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id=%1&client_secret=%2&";
const QString baiduImageUrl = "https://aip.baidubce.com/rest/2.0/image-classify/v2/advanced_general?access_token=%1";

#endif // CONFIG_H
