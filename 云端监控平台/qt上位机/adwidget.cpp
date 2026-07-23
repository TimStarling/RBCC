#include "adwidget.h"
#include "ui_adwidget.h"

AdWidget::AdWidget(QWidget *parent) :
    AbstuctWidget(parent),
    ui(new Ui::AdWidget)
{
    ui->setupUi(this);
}

AdWidget::~AdWidget()
{
    delete ui;
}

void AdWidget::on_pushButton_clicked()
{
    signalJumpWidget(TCP_WIDGET);
}
