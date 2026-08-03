#!/bin/bash

# copy & chmod
cp service/hg_wxdc.service /etc/systemd/system/hg_wxdc.service
chmod 644 /etc/systemd/system/hg_wxdc.service

# reload systemd
systemctl daemon-reload

# enable auto-start
systemctl enable hg_wxdc

# run
systemctl start hg_wxdc
systemctl status hg_wxdc
