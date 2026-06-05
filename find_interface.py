# run this first to find your interface name
# save as find_interface.py and run it

from scapy.all import get_if_list, get_if_addr

print("Available interfaces on your machine:")
print("=" * 50)

for iface in get_if_list():
    try:
        ip = get_if_addr(iface)
        print(f"  Interface: {iface}")
        print(f"  IP:        {ip}")
        print()
    except Exception:
        print(f"  Interface: {iface}")
        print(f"  IP:        (could not get IP)")
        print()