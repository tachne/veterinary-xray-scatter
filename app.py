from functools import partial

import numpy as np
import pandas as pd
import streamlit as st

from scatter import MODEL_VERSION
from scatter.model import COMPTON, ENERGIES, GROUPS, Settings, session_run
from scatter.plots import room_figure, distribution_figure
from scatter.player_view import playback_view
from scatter.playback import PLAYBACK_LIMITS
from scatter.grid_view import grid_view
from scatter.results import (LABELS, indices_for_display, materials_frame, particles, photon_csv,
                             summary, summary_csv)

st.set_page_config(page_title="散乱線の発生と方向 | Veterinary X-ray Scatter Lab", layout="wide",
                   initial_sidebar_state="auto")
st.caption("VETERINARY X-RAY SCATTER LAB　 /　 v0.2.2")
st.title("散乱線の発生と方向")
st.write("一次X線が最初に相互作用した場所と、そこから生まれた散乱光子の向きを観察します。")

with st.sidebar:
    st.header("照射条件")
    energy=st.select_slider("単色光子エネルギー (keV)", ENERGIES, value=80, key="energy")
    st.caption("XCOM原表の11点。管電圧（kVp）や管球の連続スペクトルとは異なります。")
    thick=st.slider("被写体の厚さ (cm)",0,30,12,key="thick")
    field=st.slider("正方形照射野の一辺 (cm)",6,36,24,key="field")
    st.caption("照射野は焦点から100 cmの検出器面で定義します。入射数は絞り前の40 × 40 cmに対応します。")
    n=st.number_input("入射光子数",min_value=1,max_value=100_000,value=20_000,step=1000,key="count")
    seed=st.number_input("乱数シード",min_value=0,max_value=2**32-1,value=42,step=1,key="seed")
    st.caption("同じ条件とシードで同じ標本に戻れます。")

p=Settings(energy,thick,field,n,seed)
run=session_run(st.session_state,p)
h=int(np.sum(run.part>=0))
c=int(np.sum(run.process==COMPTON))
cols=st.columns(3)
for col,cap,num in zip(cols,("入射一次光子","初回相互作用","コンプトン散乱"),(n,h,c)):
    col.metric(cap,f"{num:,} 個")
st.caption(f"{energy} keV　｜　被写体 {thick} cm　｜　照射野 {field} × {field} cm　｜　シード {seed}　"
           f"｜　無相互作用で検出器面まで到達：{n-h:,} 個")

v,grid_tab,counts,ref=st.tabs(["撮影室と飛跡","集束グリッド","計数と分布","モデルと文献"],
                              key="lab_tab", on_change="rerun")
def chart(fig,key):
    st.plotly_chart(fig,key=key,width="stretch",theme=None,config={"displayModeBar":False,"scrollZoom":False})

def legend():
    st.markdown(":blue[● 被写体]　 :green[■ 撮影台]　 :orange[◆ コリメータ周辺]　 :violet[▲ 空気]")

def photon_count(label, options, key):
    # Streamlit removes hidden widgets. Keep each view's last count in this session.
    preference = f"saved_{key}"
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get(preference, 16)
    count = st.selectbox(label, options, key=key)
    st.session_state[preference] = count
    return count

with v:
    st.subheader("撮影室の断面")
    view_mode=st.radio("飛跡の表示",("静止図","連続再生"),horizontal=True,key="view_mode")
    st.caption("焦点を原点として真下を +z とした正面投影（x–z）です。灰線は一次X線、色付き矢印はコンプトン散乱後の方向です。")
    a,b=st.columns([1.5,1])
    with a:
        sampling=st.radio("飛跡の選び方",["発生源別の例示","入射番号順"],horizontal=True,key="pick")
    with b:
        if view_mode == "静止図":
            limit = photon_count("静止図の表示光子数（上限）", (8, 16, 32, 64, 100), "limit")
        else:
            limit = photon_count("連続再生する光子数（各シード）", PLAYBACK_LIMITS, "film_limit")
    sources=st.multiselect("図に表示する発生源",GROUPS,default=list(GROUPS),key="sources")
    close=st.toggle("コリメータ周辺を拡大",key="close")
    examples=sampling=="発生源別の例示"
    if view_mode=="静止図":
        idx=indices_for_display(run,limit,[GROUPS.index(k) for k in sources],examples)
        st.markdown(f"**表示 {len(idx)} 本**　／　全入射 {n:,} 個")
    if examples:
        st.caption("全標本のコンプトン事象から、選択した発生源を順に1本ずつ選びます。希少な発生源を見やすくするための例示で、図の本数比は発生率ではありません。")
    elif view_mode == "静止図":
        st.caption("先頭から指定本数を取り、その後に発生源で絞ります。無相互作用の一次線は残ります。×は光電吸収、◇（中抜き）は干渉性散乱での追跡終了です。")
    else:
        st.caption("選択した発生源の光子と無相互作用の一次線を、入射番号順に再生します。×は光電吸収、◇は干渉性散乱の発生点です。")
    legend()
    if view_mode=="静止図" and not idx.size:
        st.info("この表示条件に該当する飛跡はありません。全標本の計数は「計数と分布」で確認できます。")
    if view_mode=="連続再生":
        playback_view(run,sources,limit,examples,close)
    else:
        chart(room_figure(run,idx,close),"room")
        st.caption("矢じりが大きいほど散乱後エネルギーが高く、発生点・矢じりに触れると角度とkeVを読めます。"
                   "矢印は3次元方向を一定長（18 cm）で投影したもので、向きによって短く見えます。先端は次の相互作用位置や測定器への到達点ではありません。")
        with st.expander("表示中の光子：座標・角度・エネルギー"):
            view=particles(run,idx,False).rename(columns={"photon_id":"光子番号","source":"発生源","component":"部位",
                                "material":"材質ID","process":"初回過程","theta_deg":"θ (°)","scattered_keV":"E′ (keV)",
                                "azimuth_local_deg":"局所方位角 (°)","recoil_keV":"反跳 (keV)"})
            st.dataframe(view,hide_index=True,width="stretch")
            st.caption("位置 (x, y, z) は cm。無相互作用は位置・過程別の出力量を空欄にします。θ、方位角、E′ はコンプトン事象のみです。")
        st.download_button("表示中の光子をCSV保存",data=partial(photon_csv,run,idx),
                           file_name=f"scatter_view_s{seed}.csv",mime="text/csv",on_click="ignore",key="view_csv")

if grid_tab.open:
    with grid_tab:
        grid_view(run)

with counts:
    st.subheader("発生源別の初回相互作用")
    st.caption("表示フィルターにかかわらず全入射光子を集計します。「入射」はその領域に一次光子のまま一度でも入った個数です。同じ光子が別領域にも入るため、入射列は足し合わせられません。")
    def table(parts=False):
        frame=pd.DataFrame(summary(run,parts))
        frame.columns=["部位" if parts else "発生源",*LABELS]
        return frame
    st.dataframe(table(),width="stretch",hide_index=True)
    st.caption(f"各光子の初回相互作用は1か所だけです。{h:,} 個と無相互作用 {n-h:,} 個を足すと、入射 {n:,} 個になります。")
    with st.expander("コリメータ内の部材別内訳"):
        st.dataframe(table(True).iloc[3:],hide_index=True,width="stretch")
    st.markdown("**散乱角とエネルギーの分布**")
    legend()
    a,b=st.columns(2)
    with a: chart(distribution_figure(run,True),"angle")
    with b: chart(distribution_figure(run,False),"energy_hist")
    st.caption("全コンプトン事象の個数。X線の発生位置における計数であり、特定の測定位置の線量や寄与率ではありません。")
    st.download_button("発生源・部位別集計CSV",data=summary_csv(run),file_name=f"scatter_counts_s{seed}.csv",
                       mime="text/csv",on_click="ignore",key="summary_csv")
    st.download_button("全入射光子CSV",data=partial(photon_csv,run),file_name=f"scatter_all_s{seed}.csv",
                       mime="text/csv",on_click="ignore",key="all_csv")
    st.caption("全入射光子CSVは1光子1行。全体集計CSVでは発生源別と部位別を別の行種別として出力します。")

with ref:
    st.subheader("何を計算しているか")
    st.markdown("**計算**　点焦点から発した単色一次光子について、通過する層の密度・実光路長・"
                "[NIST XCOM](https://physics.nist.gov/PhysRefData/Xcom/html/xcom1.html) の係数から初回相互作用を抽選します。"
                "光電吸収と干渉性散乱は発生点で追跡終了。コンプトン事象だけは非偏光・静止自由電子のKlein–Nishina分布で方向を抽選します。")
    st.latex(r"E' = \frac{E}{1+(E/511\,{\rm keV})(1-\cos\theta)}")
    st.markdown("**仮定**　上管式の一般撮影を想定し、被写体は水、撮影台はポリカーボネート板としました。"
                "部材の配置・等価厚、点焦点、絞り前照射野の均一面密度は実習用の設定で、特定の装置の実測値ではありません。"
                "ミラーは横断方向のAl等価層です。散乱するのはX線で、可視光の十字照明自体がX線を生じることはありません。")
    with st.expander(f"部材の組成・密度・厚さと {energy} keV の係数"):
        st.dataframe(materials_frame(p),width="stretch",hide_index=True)
        st.caption("係数は cm²/g、組成は元素の質量分率。各分岐は部分係数の和で規格化します。吸収端をまたぐ補間は行いません。")
    st.markdown("**対象外**　管容器からの漏洩X線、管容器自体の散乱、検出器以遠の輸送、散乱後の減弱・多重散乱、"
                "蛍光X線、電子輸送、実測線量率・安全性の判定は計算しません。部材で生じた光子がそのまま装置外に出るという意味ではありません。")
    st.subheader("先行研究で測った量")
    st.markdown("[Chidaら（AJR, 2011）](https://doi.org/10.2214/AJR.10.6396) は血管造影系のピンホール像から、"
                "ファントム・支持台付近とコリメータ出口に発生源を認めました。カバーと面積線量計の取り外しで位置を検証した研究です。")
    st.markdown("[Taoら（Medical Physics, 2019、§2.4・図7）](https://doi.org/10.1002/mp.13720) の **5〜56%** は、"
                "血管造影装置4台・RAO/LAO −90°〜＋90°で、床上150 cm、アイソセンタから側方40 cm・足側60 cmの電離箱で評価した値です。"
                "分母は同じ測定点の全散乱空気カーマ（KAP規格化）。獣医装置の発生率や、本アプリの設定値には使用していません。")
    st.caption(f"モデル {MODEL_VERSION}　｜　データと計算はオフラインで動作します。")
