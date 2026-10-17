@echo off
rem Double-click: start the cluster bench and the car panel (software\linux\sim\start_car_sim.sh in the Ubuntu-24.04 WSL distro).
wsl.exe -d Ubuntu-24.04 -u root -e bash /mnt/c/Users/root/Project/cluster-pcb/software/linux/sim/start_car_sim.sh
