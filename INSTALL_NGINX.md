# Nginx installation and setup for CCTV Dashboard

This guide installs Nginx on Raspberry Pi OS and serves the dashboard from the `cctv-dashboard` folder on port `8880`.

## 1. Project folder layout

cctv-dashboard/
  index.html
  README.md
  INSTALL_NGINX.md
  assets/
  config/
    nginx-cctv-dashboard.conf
  scripts/
    install-nginx.sh

## 2. Install Nginx on Raspberry Pi 5

Run the following commands on the Pi:

```bash
sudo apt update
sudo apt install -y nginx
```

## 3. Copy the dashboard files

Place the project in the expected path:

```bash
mkdir -p /home/pi/cctv
cd /home/pi/cctv
# copy or clone the cctv-dashboard folder here
```

Expected root path:

```bash
/home/pi/cctv/cctv-dashboard
```

## 4. Enable the dashboard site

Create the Nginx site file with the provided config:

```bash
sudo cp /home/pi/cctv/cctv-dashboard/config/nginx-cctv-dashboard.conf /etc/nginx/sites-available/cctv-dashboard
sudo ln -sf /etc/nginx/sites-available/cctv-dashboard /etc/nginx/sites-enabled/cctv-dashboard
sudo rm -f /etc/nginx/sites-enabled/default
```

## 5. Verify and start Nginx

```bash
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx
```

## 6. Test the dashboard

Open the browser on the Pi or another machine on the same network:

```text
http://<PI_IP_ADDRESS>:8880/
```

You should see the CCTV Dashboard start page.

## 7. Optional helper script

You can run the helper script included in this project:

```bash
chmod +x /home/pi/cctv/cctv-dashboard/scripts/install-nginx.sh
/home/pi/cctv/cctv-dashboard/scripts/install-nginx.sh
```
