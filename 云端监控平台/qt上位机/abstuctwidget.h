#ifndef ABSTUCTWIDGET_H
#define ABSTUCTWIDGET_H

#include <QWidget>
#include "config.h"

class AbstuctWidget : public QWidget
{
    Q_OBJECT
public:
    explicit AbstuctWidget(QWidget *parent = nullptr);

signals:
    //提供统一规范的界面跳转接口
    void signalJumpWidget(WidgetIndex index);


public slots:
};

#endif // ABSTUCTWIDGET_H
