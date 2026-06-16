"""
gen_images.py
Generates 3D-style cyberpunk/neon visuals for the Network Guardian ICWITE PPT.
Run: python gen_images.py
All images saved to: ./ppt_images/
"""
import os, math, numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Arc
import matplotlib.patheffects as pe
from matplotlib.colors import LinearSegmentedColormap
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import warnings
warnings.filterwarnings('ignore')

OUT = r"c:\Users\adina\OneDrive\Desktop\cnfinal\ppt_images"
os.makedirs(OUT, exist_ok=True)

BG    = '#0A1628'
CYAN  = '#38BDF8'
CYAN2 = '#5BC8FF'
WHITE = '#FFFFFF'
GLOW  = '#1E88E5'
GREEN = '#00FF80'

def save(fig, name, dpi=150):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=dpi, bbox_inches='tight',
                facecolor=BG, edgecolor='none')
    plt.close(fig)
    print(f"  Saved: {name}")
    return path

def glow_text(ax, x, y, s, fs=16, color=CYAN, ha='center', va='center',
              weight='bold', alpha_glow=0.3, n_glow=3):
    for i in range(n_glow, 0, -1):
        ax.text(x, y, s, fontsize=fs+i*2, ha=ha, va=va, color=color,
                fontweight=weight, alpha=alpha_glow/i,
                transform=ax.transData if hasattr(ax,'transData') else ax.transAxes)
    ax.text(x, y, s, fontsize=fs, ha=ha, va=va, color=color,
            fontweight=weight)


# ─── IMAGE 1: Glowing Shield — Title Slide ────────────────────────────────────
def img_shield():
    fig, ax = plt.subplots(figsize=(6, 6), facecolor=BG)
    ax.set_facecolor(BG); ax.set_xlim(-1.2, 1.2); ax.set_ylim(-1.4, 1.3)
    ax.axis('off')

    # Outer glow rings
    for r, a in [(1.1, 0.05), (1.0, 0.10), (0.92, 0.18)]:
        c = plt.Circle((0, 0), r, color=GLOW, fill=False,
                        linewidth=10*a*8, alpha=a)
        ax.add_patch(c)

    # Shield shape via polygon
    shield_x = [0, 0.75, 0.75, 0.55, 0, -0.55, -0.75, -0.75, 0]
    shield_y = [1.1, 0.8, 0.1, -0.5, -1.1, -0.5, 0.1, 0.8, 1.1]
    from matplotlib.patches import Polygon
    # glow behind shield
    for off, al in [(0.07, 0.08), (0.04, 0.15), (0.02, 0.25)]:
        sx = [x*(1+off) for x in shield_x]
        sy = [y*(1+off) for y in shield_y]
        poly = Polygon(list(zip(sx, sy)), closed=True,
                       facecolor=GLOW, edgecolor='none', alpha=al)
        ax.add_patch(poly)
    # shield fill
    poly = Polygon(list(zip(shield_x, shield_y)), closed=True,
                   facecolor='#0D2545', edgecolor=CYAN, linewidth=2.5, alpha=0.95)
    ax.add_patch(poly)

    # Network nodes inside shield
    nodes = [(0, 0.3), (-0.3, -0.1), (0.3, -0.1),
             (0, -0.55), (-0.15, 0.6), (0.15, 0.6)]
    edges = [(0,1),(0,2),(0,3),(1,3),(2,3),(0,4),(0,5),(4,5)]
    for i,j in edges:
        ax.plot([nodes[i][0], nodes[j][0]],
                [nodes[i][1], nodes[j][1]],
                color=CYAN, lw=1.5, alpha=0.6)
    for nx_, ny_ in nodes:
        ax.scatter(nx_, ny_, s=120, c=CYAN, zorder=5, alpha=0.9)
        ax.scatter(nx_, ny_, s=300, c=CYAN, zorder=4, alpha=0.15)

    # Lock icon in center
    glow_text(ax, 0, 0, '🔒', fs=28, color=WHITE, weight='normal')

    # Pulse rings
    for r, a in [(0.15, 0.7), (0.25, 0.4), (0.38, 0.2)]:
        c = plt.Circle((0, 0), r, color=CYAN, fill=False,
                        linewidth=1.5, alpha=a, linestyle='--')
        ax.add_patch(c)

    save(fig, 'img_shield.png', dpi=180)

img_shield()


# ─── IMAGE 2: 5-Layer 3D Stack — Architecture ─────────────────────────────────
def img_3d_stack():
    fig = plt.figure(figsize=(7, 5), facecolor=BG)
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor(BG)

    layer_cols = ['#0E3A6B','#0B4D4A','#2D1B6B','#5A1A1A','#0C3B1C']
    layer_lbls = ['Web Dashboard','Mitigator','LLM Analyzer',
                  'Attack Detector','Network Sniffer']
    w, d = 4.0, 2.0
    for i, (col, lbl) in enumerate(zip(layer_cols, layer_lbls)):
        z0 = i * 0.55
        # platform face
        verts = [[(0,0,z0),(w,0,z0),(w,d,z0),(0,d,z0)]]
        poly = Poly3DCollection(verts, alpha=0.85,
                                facecolor=col, edgecolor=CYAN)
        poly.set_linewidth(1.2)
        ax.add_collection3d(poly)
        # top edge highlight
        verts2 = [[(0,0,z0+0.45),(w,0,z0+0.45),
                   (w,d,z0+0.45),(0,d,z0+0.45)]]
        poly2 = Poly3DCollection(verts2, alpha=0.3,
                                 facecolor=CYAN, edgecolor=CYAN)
        ax.add_collection3d(poly2)
        # label
        ax.text(w/2, d/2, z0+0.22, lbl,
                ha='center', va='center',
                color=WHITE, fontsize=8, fontweight='bold')

    ax.set_xlim(0, w); ax.set_ylim(0, d); ax.set_zlim(0, 3.2)
    ax.set_axis_off()
    ax.view_init(elev=20, azim=-55)
    fig.patch.set_facecolor(BG)
    save(fig, 'img_stack.png', dpi=160)

img_3d_stack()


# ─── IMAGE 3: Attack Radar Chart — Detection Engine ───────────────────────────
def img_radar():
    categories = ['ICMP\nFlood','SYN\nFlood','UDP\nFlood',
                  'Port\nScan','IP Frag']
    N = len(categories)
    angles = [n/float(N)*2*math.pi for n in range(N)]
    angles += angles[:1]

    # Values: severity (0-10 scale)
    detected = [9.5, 8.5, 9.0, 7.5, 8.0]
    detected += detected[:1]
    normal   = [1.0, 0.5, 1.0, 0.5, 0.2]
    normal   += normal[:1]

    fig, ax = plt.subplots(figsize=(5.5, 5.5), subplot_kw=dict(polar=True),
                           facecolor=BG)
    ax.set_facecolor(BG)
    ax.spines['polar'].set_color(GLOW)
    ax.spines['polar'].set_alpha(0.5)

    # Grid rings
    ax.set_rlabel_position(0)
    ax.set_ylim(0, 10)
    for rl in [2,4,6,8,10]:
        ax.plot(angles, [rl]*len(angles), color=GLOW, lw=0.5, alpha=0.3)

    # Gridlines
    ax.set_thetagrids([a*180/math.pi for a in angles[:-1]], categories,
                       fontsize=11, color=CYAN)
    for lbl in ax.get_xticklabels():
        lbl.set_color(CYAN)
        lbl.set_fontweight('bold')
    ax.set_yticks([])

    # Normal traffic fill
    ax.fill(angles, normal, alpha=0.15, color=WHITE)
    ax.plot(angles, normal, color=WHITE, lw=1.5, alpha=0.5,
            linestyle='--', label='Normal traffic')

    # Attack fill (glow effect)
    for al in [0.05, 0.10, 0.20]:
        ax.fill(angles, detected, alpha=al, color=CYAN)
    ax.plot(angles, detected, color=CYAN, lw=2.5, label='Under attack')

    ax.scatter(angles[:-1], detected[:-1], s=80, color=CYAN,
               zorder=5, edgecolors=WHITE, linewidth=0.8)

    ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.1),
              facecolor=BG, edgecolor=GLOW, labelcolor=WHITE, fontsize=10)
    fig.patch.set_facecolor(BG)
    save(fig, 'img_radar.png', dpi=160)

img_radar()


# ─── IMAGE 4: LLM Neural Net — LLM Analyzer ──────────────────────────────────
def img_neural():
    fig, ax = plt.subplots(figsize=(7, 5), facecolor=BG)
    ax.set_facecolor(BG); ax.set_xlim(-0.5, 5.5); ax.set_ylim(-0.5, 4.5)
    ax.axis('off')

    layer_sizes = [3, 5, 5, 3]
    layer_x = [0.5, 1.8, 3.2, 4.5]
    layer_names = ['Input\n(Threat)', 'Hidden\nLayer 1', 'Hidden\nLayer 2',
                   'Output\n(JSON)']
    node_cols = [GLOW, '#4B0082', '#4B0082', GREEN]
    node_pos = {}

    for li, (lsize, lx, col) in enumerate(zip(layer_sizes, layer_x, node_cols)):
        ys = np.linspace(0.5, 3.5, lsize)
        for ni, y in enumerate(ys):
            nid = (li, ni)
            node_pos[nid] = (lx, y)
            # glow
            for r, a in [(0.18, 0.08), (0.12, 0.15)]:
                c = Circle((lx, y), r, color=col, fill=True, alpha=a)
                ax.add_patch(c)
            c = Circle((lx, y), 0.10, color=col, fill=True, alpha=0.9)
            ax.add_patch(c)
            c = Circle((lx, y), 0.10, color=WHITE, fill=False,
                        linewidth=0.8, alpha=0.5)
            ax.add_patch(c)

    # Connections
    for li in range(len(layer_sizes)-1):
        s, t = li, li+1
        for ni in range(layer_sizes[s]):
            for nj in range(layer_sizes[t]):
                xs, ys_ = node_pos[(s,ni)]
                xt, yt  = node_pos[(t,nj)]
                alpha = 0.15 + 0.05*np.random.random()
                ax.plot([xs,xt],[ys_,yt], color=CYAN,
                        lw=0.6, alpha=alpha)

    # Layer labels
    for lx, name in zip(layer_x, layer_names):
        ax.text(lx, -0.25, name, ha='center', va='top',
                color=CYAN, fontsize=9, fontweight='bold')

    # Title
    ax.text(2.5, 4.3, 'TinyLlama 1.1B Parameter LLM',
            ha='center', color=WHITE, fontsize=11, fontweight='bold')

    # Input/output labels
    inp = ['IP: 203.0.113.50', 'Type: SYN Flood', 'Count: 87 pps']
    for i, lbl in enumerate(inp):
        y = node_pos[(0,i)][1]
        ax.text(-0.3, y, lbl, ha='right', va='center',
                color=LIGHT, fontsize=8) if False else None
        ax.annotate(lbl, xy=(0.45,y), ha='right', va='center',
                    color=WHITE, fontsize=7.5,
                    xycoords='data')

    out_lbls = ['"attack"', '"explanation"', '"mitigation"']
    LIGHT = '#CBD5E1'
    for i, lbl in enumerate(out_lbls):
        y = node_pos[(3,i)][1]
        ax.annotate(lbl, xy=(4.55, y), ha='left', va='center',
                    color=GREEN, fontsize=8, fontweight='bold',
                    xycoords='data')

    fig.patch.set_facecolor(BG)
    save(fig, 'img_neural.png', dpi=160)

img_neural()


# ─── IMAGE 5: Pipeline Timing Bar Chart — Results ────────────────────────────
def img_timing():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4.5), facecolor=BG)

    # Left: detection latency per attack
    attacks = ['ICMP', 'SYN', 'UDP', 'Port\nScan', 'Frag']
    means   = [0.14, 0.27, 0.15, 0.51, 0.21]
    mins_   = [0.11, 0.23, 0.12, 0.45, 0.18]
    maxs_   = [0.19, 0.34, 0.21, 0.62, 0.27]
    errs    = [[m-mn for m,mn in zip(means,mins_)],
               [mx-m for m,mx in zip(means,maxs_)]]

    ax1.set_facecolor(BG)
    bars = ax1.bar(attacks, means, color=GLOW, alpha=0.85,
                   edgecolor=CYAN, linewidth=1.2, width=0.55)
    ax1.errorbar(attacks, means, yerr=errs, fmt='none',
                 color=WHITE, capsize=5, capthick=1.5, elinewidth=1.5)
    # glow on bars
    for bar in bars:
        h = bar.get_height()
        ax1.bar(bar.get_x()+bar.get_width()/2, h,
                width=bar.get_width()+0.15, alpha=0.08,
                color=CYAN, edgecolor='none')

    for xi, (x, v) in enumerate(zip(attacks, means)):
        ax1.text(xi, v+0.015, f'{v:.2f}s', ha='center',
                 color=CYAN, fontsize=10, fontweight='bold')

    ax1.set_facecolor(BG)
    ax1.spines['bottom'].set_color(GLOW); ax1.spines['left'].set_color(GLOW)
    ax1.spines['top'].set_visible(False); ax1.spines['right'].set_visible(False)
    ax1.tick_params(colors=WHITE, labelsize=9)
    ax1.set_ylabel('Detection Time (s)', color=WHITE, fontsize=10)
    ax1.set_title('Detection Latency by Attack Type', color=CYAN,
                  fontsize=11, fontweight='bold', pad=10)
    ax1.set_ylim(0, 0.75)
    ax1.yaxis.label.set_color(WHITE)
    for lbl in ax1.get_xticklabels():
        lbl.set_color(WHITE)

    # Right: pie chart for pipeline stages
    labels2 = ['Detection\n0.25 s', 'LLM Analysis\n2.46 s', 'Mitigation\n0.17 s']
    sizes   = [8.7, 85.4, 5.9]
    colors2 = [GLOW, '#7B1FA2', '#0B4D4A']
    explode = (0.02, 0.06, 0.02)

    ax2.set_facecolor(BG)
    wedges, texts, autotexts = ax2.pie(
        sizes, labels=labels2, colors=colors2, explode=explode,
        autopct='%1.1f%%', startangle=90,
        wedgeprops={'edgecolor': CYAN, 'linewidth': 1.5},
        textprops={'color': WHITE, 'fontsize': 9},
        pctdistance=0.72)
    for at in autotexts:
        at.set_color(WHITE); at.set_fontsize(9); at.set_fontweight('bold')
    ax2.set_title('Total Response: 2.88 s\n(Pipeline Breakdown)',
                  color=CYAN, fontsize=11, fontweight='bold')

    fig.patch.set_facecolor(BG)
    plt.tight_layout(pad=2)
    save(fig, 'img_timing.png', dpi=160)

img_timing()


# ─── IMAGE 6: Network Packet Flow Diagram ─────────────────────────────────────
def img_network():
    fig, ax = plt.subplots(figsize=(9, 4.5), facecolor=BG)
    ax.set_facecolor(BG); ax.axis('off')
    ax.set_xlim(0, 10); ax.set_ylim(0, 5)

    # Nodes
    nodes = {
        'Attacker':    (0.9, 2.5),
        'Network\nSniffer': (2.8, 2.5),
        'Attack\nDetector': (4.8, 3.5),
        'LLM\nAnalyzer':    (6.8, 3.5),
        'Mitigator':        (8.7, 3.5),
        'Web\nDashboard':   (6.8, 1.2),
    }
    node_cols = {
        'Attacker': '#8B0000',
        'Network\nSniffer': GLOW,
        'Attack\nDetector': '#4B0082',
        'LLM\nAnalyzer': '#1B5E20',
        'Mitigator': '#B71C1C',
        'Web\nDashboard': '#0D47A1',
    }
    edges = [
        ('Attacker', 'Network\nSniffer', 'Malicious\npackets', '#FF4444'),
        ('Network\nSniffer', 'Attack\nDetector', 'PacketMetadata', CYAN),
        ('Attack\nDetector', 'LLM\nAnalyzer', 'ThreatEvent', '#CE93D8'),
        ('LLM\nAnalyzer', 'Mitigator', 'Block\ncommand', '#FF8A65'),
        ('Network\nSniffer', 'Web\nDashboard', 'Live feed', '#64B5F6'),
        ('Attack\nDetector', 'Web\nDashboard', 'Alerts', '#64B5F6'),
        ('Mitigator', 'Web\nDashboard', 'Status', '#64B5F6'),
    ]

    for src, dst, lbl, col in edges:
        xs, ys = nodes[src]; xt, yt = nodes[dst]
        ax.annotate('', xy=(xt, yt), xytext=(xs, ys),
                    arrowprops=dict(arrowstyle='->', color=col,
                                   lw=2.0, connectionstyle='arc3,rad=0.1'))
        mx, my = (xs+xt)/2, (ys+yt)/2
        ax.text(mx, my+0.15, lbl, ha='center', va='bottom',
                color=col, fontsize=7.5, fontstyle='italic')

    for name, (nx_, ny_) in nodes.items():
        col = node_cols[name]
        for r, a in [(0.55, 0.05), (0.42, 0.10)]:
            c = Circle((nx_, ny_), r, color=col, fill=True, alpha=a)
            ax.add_patch(c)
        c = Circle((nx_, ny_), 0.35, color=col, fill=True, alpha=0.85)
        ax.add_patch(c)
        c = Circle((nx_, ny_), 0.35, color=CYAN, fill=False, linewidth=1.5)
        ax.add_patch(c)
        ax.text(nx_, ny_, name, ha='center', va='center',
                color=WHITE, fontsize=7.5, fontweight='bold',
                multialignment='center')

    ax.set_title('Network Guardian — System Data Flow',
                 color=CYAN, fontsize=13, fontweight='bold', pad=8)
    fig.patch.set_facecolor(BG)
    save(fig, 'img_network.png', dpi=160)

img_network()


# ─── IMAGE 7: Comparison Bar Chart ────────────────────────────────────────────
def img_comparison():
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=BG)
    ax.set_facecolor(BG)

    systems = ['Snort\n[11]', 'Anomaly\nIDS [12]', 'DNN/ML\nIDS [13]',
               'LIME/SHAP\n[14,15]', 'Network\nGuardian\n(Ours)']
    # Scores across dimensions (0-3: 0=No, 1=Partial, 2=Good, 3=Best)
    detection    = [2, 2, 2.5, 2, 2.5]
    explainability= [0, 0, 0, 1, 3]
    auto_mitig   = [0, 0, 0, 0, 3]
    speed        = [0, 0, 0, 0, 2.8]

    x = np.arange(len(systems))
    w = 0.18
    bars_d = ax.bar(x - 1.5*w, detection,     w, label='Detection',     color=GLOW, alpha=0.85, edgecolor=CYAN, lw=0.8)
    bars_e = ax.bar(x - 0.5*w, explainability, w, label='Explainability', color='#7B1FA2', alpha=0.85, edgecolor=CYAN, lw=0.8)
    bars_m = ax.bar(x + 0.5*w, auto_mitig,    w, label='Auto Mitigation',color='#0B4D4A', alpha=0.85, edgecolor=CYAN, lw=0.8)
    bars_s = ax.bar(x + 1.5*w, speed,         w, label='Speed Score',   color='#5A1A1A', alpha=0.85, edgecolor=CYAN, lw=0.8)

    # Highlight our bar group
    ax.axvspan(3.6, 4.4, alpha=0.08, color=GREEN)

    ax.set_xticks(x); ax.set_xticklabels(systems, color=WHITE, fontsize=9)
    ax.set_ylabel('Score (0–3)', color=WHITE, fontsize=10)
    ax.set_ylim(0, 3.6)
    ax.set_title('Capability Comparison Across IDS Approaches',
                 color=CYAN, fontsize=12, fontweight='bold', pad=8)
    ax.spines['bottom'].set_color(GLOW); ax.spines['left'].set_color(GLOW)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.tick_params(colors=WHITE, labelsize=9)
    ax.legend(facecolor='#0E2040', edgecolor=GLOW,
              labelcolor=WHITE, fontsize=9, loc='upper left')

    # Label "Ours" marker
    ax.text(4, 3.3, '★ Ours', ha='center', color=GREEN,
            fontsize=11, fontweight='bold')

    fig.patch.set_facecolor(BG)
    plt.tight_layout()
    save(fig, 'img_comparison.png', dpi=160)

img_comparison()


# ─── IMAGE 8: Wireshark Packet Capture Visual ─────────────────────────────────
def img_wireshark():
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=BG)
    ax.set_facecolor(BG); ax.axis('off')

    # Timeline
    t = np.linspace(0, 10, 500)
    # Normal traffic before block
    y_normal = np.random.poisson(2, 500).astype(float)
    y_normal[:200] += np.random.poisson(150, 200).astype(float)  # attack
    y_normal[250:] = np.random.poisson(0.5, 250).astype(float)   # after block
    # Smooth
    from scipy.ndimage import gaussian_filter1d
    y_smooth = gaussian_filter1d(y_normal.astype(float), sigma=5)

    ax2 = fig.add_axes([0.08, 0.18, 0.88, 0.68])
    ax2.set_facecolor(BG)
    ax2.fill_between(t, y_smooth, alpha=0.25, color=CYAN)
    ax2.plot(t, y_smooth, color=CYAN, lw=2)

    # Attack zone
    ax2.axvspan(0, 4.8, alpha=0.06, color='#FF4444')
    ax2.axvline(4.8, color='#FF4444', lw=2, linestyle='--', alpha=0.8)
    ax2.text(2.4, max(y_smooth)*0.9, 'ATTACK TRAFFIC\n150+ pps',
             ha='center', color='#FF6666', fontsize=10, fontweight='bold')
    ax2.text(5.0, max(y_smooth)*0.9, 'BLOCK APPLIED\n→ 0 pps',
             ha='left', color=GREEN, fontsize=10, fontweight='bold')

    # Block applied marker
    ax2.annotate('route add\n(block)', xy=(4.8, y_smooth[240]),
                 xytext=(5.5, max(y_smooth)*0.6),
                 arrowprops=dict(arrowstyle='->', color='#FF6666', lw=1.5),
                 color='#FF6666', fontsize=9, fontweight='bold')

    # 60s revert
    ax2.axvline(9.8, color=CYAN, lw=1.5, linestyle=':', alpha=0.7)
    ax2.text(9.8, max(y_smooth)*0.5, ' 60s\n revert',
             color=CYAN, fontsize=8)

    ax2.set_xlabel('Time (seconds)', color=WHITE, fontsize=10)
    ax2.set_ylabel('Packets per Second', color=WHITE, fontsize=10)
    ax2.set_title('Wireshark Validation — SYN Flood Traffic Capture',
                  color=CYAN, fontsize=12, fontweight='bold', pad=8)
    ax2.spines['bottom'].set_color(GLOW); ax2.spines['left'].set_color(GLOW)
    ax2.spines['top'].set_visible(False); ax2.spines['right'].set_visible(False)
    ax2.tick_params(colors=WHITE)

    fig.patch.set_facecolor(BG)
    save(fig, 'img_wireshark.png', dpi=160)

img_wireshark()


# ─── IMAGE 9: Attack Types 3D Cylinder Chart ──────────────────────────────────
def img_attacks3d():
    fig = plt.figure(figsize=(9, 5), facecolor=BG)
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor(BG)

    attacks  = ['ICMP\nFlood', 'SYN\nFlood', 'UDP\nFlood',
                'Port\nScan', 'IP Frag']
    thresh   = [20, 20, 20, 10, 10]
    observed = [150, 87, 140, 52, 45]
    colors_  = ['#E53935','#7B1FA2','#1565C0','#2E7D32','#E65100']

    xs = np.arange(len(attacks))
    width = 0.35
    for xi, (t, o, col) in enumerate(zip(thresh, observed, colors_)):
        # Threshold bar
        ax.bar3d(xi-0.22, 0, 0, 0.35, 0.4, t, color='#1E5F88',
                 alpha=0.5, shade=True)
        # Observed bar
        ax.bar3d(xi+0.02, 0, 0, 0.35, 0.4, o, color=col,
                 alpha=0.85, shade=True)
        ax.text(xi, 0.5, o+5, f'{o}\npps',
                ha='center', color=WHITE, fontsize=7.5, fontweight='bold')
        ax.text(xi, -0.3, 0, attacks[xi],
                ha='center', color=CYAN, fontsize=7.5, fontweight='bold')

    ax.set_zlabel('pps', color=WHITE, fontsize=9, labelpad=5)
    ax.set_title('Attack Rate: Observed vs. Threshold',
                 color=CYAN, fontsize=11, fontweight='bold', pad=10)
    ax.tick_params(colors=WHITE, labelsize=8)
    ax.set_xticks([]); ax.xaxis.label.set_color(WHITE)
    ax.yaxis.set_visible(False)
    ax.zaxis.label.set_color(WHITE)
    ax.set_zlim(0, 180)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor='#1E5F88', label='Threshold'),
                       Patch(facecolor='#E53935', label='Observed (attack)')]
    ax.legend(handles=legend_elements, loc='upper left',
              facecolor='#0E2040', edgecolor=GLOW,
              labelcolor=WHITE, fontsize=9)

    ax.view_init(elev=20, azim=-50)
    fig.patch.set_facecolor(BG)
    save(fig, 'img_attacks3d.png', dpi=160)

img_attacks3d()


print("\nAll images generated successfully!")
print(f"Location: {OUT}")
