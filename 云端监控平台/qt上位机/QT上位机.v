digraph QT_Upper_Computer {
    graph [
        label="QT上位机运行逻辑框图",
        labelloc=t,
        fontsize=26,
        fontname="SimHei",
        rankdir=LR,
        bgcolor="white",
        pad=0.35,
        nodesep=0.52,
        ranksep=0.62,
        splines=ortho
    ];

    node [
        shape=box,
        style="rounded",
        fontname="SimHei",
        fontsize=15,
        color="black",
        penwidth=1.2,
        margin="0.12,0.08"
    ];

    edge [
        fontname="SimHei",
        fontsize=12,
        color="black",
        arrowsize=0.65,
        penwidth=1.1
    ];

    main [
        label="上位机\nMainWindow"
    ];

    pages [
        label="页面管理\nQStackedWidget"
    ];

    ad [
        label="AD页面\n系统首页"
    ];

    tcp [
        label="TCP页面\nIP: 192.168.138.131\n端口: 8888"
    ];

    sort [
        label="Sort分拣页面"
    ];

    jump [
        label="页面跳转信号\nsignalJumpWidget(index)"
    ];

    tcpConnect [
        label="TCP连接模块\nQTcpSocket\n连接/断开/收发/错误处理"
    ];

    autoJump [
        label="连接成功\n3秒后跳转分拣页面"
    ];

    camera [
        label="摄像头模块\nQCamera\nQCameraViewfinder\nQCameraImageCapture"
    ];

    capture [
        label="图片采集\n按下分拣按钮\n保存图片"
    ];

    image [
        label="图片编码\n转Base64"
    ];

    model [
        label="识别模型接口\n获取token\n上传图片\n解析JSON结果"
    ];

    result [
        label="结果显示\n文本框显示识别物品"
    ];

    judge [
        label="判断结果\n是否为“手表”",
        shape=diamond
    ];

    send [
        label="发送分拣指令\nTCP发送字符“1”"
    ];

    server [
        label="服务器/下位机\n接收指令并执行动作"
    ];

    close [
        label="资源释放\n关闭摄像头/关闭软件\n停止并删除相机对象"
    ];

    main -> pages;
    pages -> ad;
    pages -> tcp;
    pages -> sort;
    ad -> jump;
    tcp -> jump;
    sort -> jump;
    jump -> pages;

    tcp -> tcpConnect;
    tcpConnect -> autoJump;
    autoJump -> sort;

    sort -> camera;
    camera -> capture;
    capture -> image;
    image -> model;
    model -> result;
    result -> judge;
    judge -> send [label="是"];
    judge -> result [label="否"];
    send -> tcpConnect;
    tcpConnect -> server;

    sort -> close;
    main -> close;
}
