#ifndef ADWIDGET_H
#define ADWIDGET_H

#include "abstuctwidget.h"

namespace Ui {
class AdWidget;
}

class AdWidget : public AbstuctWidget
{
    Q_OBJECT

public:
    explicit AdWidget(QWidget *parent = nullptr);
    ~AdWidget();

private slots:
    void on_pushButton_clicked();

private:
    Ui::AdWidget *ui;
};

#endif // ADWIDGET_H
