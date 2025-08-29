* Github
    * `https://github.com/tchapi/markdown-cheatsheet/blob/master/README.md`
* Pi temperature
    * `vcgencmd measure_temp`
* watch the Pi's cooling fan speed
    * `watch -n 1 cat /sys/devices/platform/cooling_fan/hwmon/*/fan1_input`
* Stress test the Pi
    * `s-tui`
* git
    * in iot-setup... `git pull origin main`
* Docker (https://docs.docker.com/get-started/docker_cheatsheet.pdf)
    * `docker compose build`
    * `docker compose up -d`
    * `docker ps`
    * `docker compose logs`
    * `docker compose logs --follow | ccze -A`
    * `docker compose logs -f prometheus_edge`
* fix bind mount permission issues
    * `docker compose run --rm thingsboard-edge sh` or `docker run --rm -it --entrypoint sh prom/prometheus:latest`
    * `id thingsboard`
        * You should get output like: `uid=799(thingsboard) gid=799(thingsboard) groups=799(thingsboard)`1
    * or `id` gives `uid=65534(nobody) gid=65534(nobody) groups=65534(nobody)`
    * `exit`
    * set the correct permissions:
        * `sudo chown -R 799:799 ./iot_data/tb_edge_data`
        * `sudo chown -R 799:799 ./iot_data/tb_edge_logs`
        * `sudo chown -R 1001:1001 ./iot_data/kafka-data`
        * `:~/iot-setup/edge $ sudo chown -R 65534:65534 prometheus`
            * and `:~/iot-setup/edge/iot_data $ sudo chown -R 65534:65534 prometheus`
* SSL certificate
   * First, add an allow all indounnd rule on port 80.
   * To renew `sudo certbot renew`
   * then `sudo cat /etc/letsencrypt/live/droplet.bounceme.net/fullchain.pem /etc/letsencrypt/live/droplet.bounceme.net/privkey.pem | sudo tee /usr/share/tb-haproxy/certs.d/droplet.bounceme.net.pem >/dev/null`
   * then `sudo systemctl restart haproxy`
* DNS 
   * Used noip.com for free DNS
     


