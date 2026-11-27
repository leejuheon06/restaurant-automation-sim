"""Shared print-friendly chart style for documentation figures."""
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

BLUE = '#287DAB'
ORANGE = '#E78B45'
TEAL = '#2C9B8F'
INK = '#24364B'

def setup():
    font = FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False,
        'font.size':10.5,'axes.titlesize':13,'axes.titleweight':'bold',
        'axes.titlepad':16,'text.color':INK,'axes.labelcolor':INK,
        'xtick.color':'#526579','ytick.color':'#526579','axes.edgecolor':'#D7E0E8',
        'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,
        'figure.facecolor':'#F5F8FB','axes.facecolor':'white','savefig.facecolor':'#F5F8FB',
        'legend.frameon':False,'legend.fontsize':9,'xtick.major.size':0,'ytick.major.size':0})

def polish(fig):
    for ax in fig.axes:
        ax.set_axisbelow(True)
        ax.grid(axis='y',color='#E7EDF3',linewidth=.7)
        ax.spines['bottom'].set_color('#CFD9E3')
        ax.tick_params(pad=8)
        for rect in ax.patches:
            if hasattr(rect,'set_linewidth'): rect.set_linewidth(0)
