#ifndef IMAGE_H
#define IMAGE_H

#include <QString>

class Image
{
public:
    Image();

    static QByteArray imageToBase64(QString imgPath);
};

#endif // IMAGE_H
