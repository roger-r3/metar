/usr/bin/sudo pkill -F /home/pi/metar/offpid.pid
/usr/bin/sudo pkill -F /home/pi/metar/metarpid.pid
/usr/bin/sudo /usr/bin/python3 /home/pi/metar/metar.py & echo $! > /home/pi/metar/metarpid.pid
