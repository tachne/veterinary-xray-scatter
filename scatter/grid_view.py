from functools import partial

import numpy as np
import streamlit as st

from .grid import (Grid, RATIOS, GAP, LEAD, PITCH, HALF_WIDTH, GRID_VERSION, OUTCOMES,
                   add_grid_columns, grid_csv, session_projection)
from .downstream import arrival_share, angle_figure, detector_distributions, paired_movie_events
from .grid_display import (comparison_figure, default_detail_id, grid_scene,
                           selection_projection)
from .playback import (MAX_SHOW, PLAYBACK_LIMITS, pools_for, selected_frame,
                       selections, tracks_payload)
from .player_view import _player
from .plots import ARROW_CM, COLORS
from .model import GROUPS, PARTS, ENERGY_NAMES
from .results import encode


def grid_movie(run, grid, limit):
    mode = st.radio("グリッド再生の標本", ("固定シード", "シード連続（1 → 2 → 3）"),
                    horizontal=True,key="grid_seeds")
    sequence = mode.startswith("シード連続")
    pools = pools_for(st.session_state, run, sequence, capacity=MAX_SHOW)
    selected = selections(pools, limit, range(len(GROUPS)), False, fill_ordered=True)
    raw = tracks_payload(selected)
    frame = selected_frame(selected)
    pair = selection_projection(frame, raw, grid)
    events, with_grid = paired_movie_events(selected, pair, raw, frame)
    active_seeds = [p.seed for p,_ in selected]
    settings = run.settings
    signature = ["grid", settings.energy, settings.thickness, settings.field, settings.count,
                 active_seeds, limit, grid.ratio, grid.focus, grid.sid]
    data = dict(signature=signature, pairedGrid=True, events=events, eventsWith=with_grid,
                scene=grid_scene(run,grid,False), sceneWith=grid_scene(run,grid,True),
                samples=[dict(seed=p.seed,count=p.count,shown=len(ids)) for p,ids in selected],
                colors=COLORS, groups=GROUPS, parts=PARTS, processes=ENERGY_NAMES,
                length=ARROW_CM, incidentEnergy=settings.energy)
    data["gridGeometry"] = dict(top=grid.top, height=grid.height, focus=grid.focus, sid=grid.sid,
                                gap=GAP, foil=LEAD, pitch=PITCH, halfWidth=HALF_WIDTH)
    st.caption(f"入射番号順に各標本の先頭 {min(limit, settings.count)} 個、合計 {len(events)} 個を再生します。"
               "シードをまたぐと図の履歴を消去します。左右は同じ光子番号・倍率で同期します。下の再生カウンターはこの表示標本だけを数えます。")
    _player(key="grid_player",data=data)
    st.caption("灰色は一次線、散乱線の色は被写体・撮影台・コリメータ周辺・空気に対応します。"
               "撮影室図の赤い×は最初の鉛箔接触、緑の○は検出器面。入口に向かわない散乱線は既存の18 cm以下の方向表示です。"
               "速度は観察用の表示倍率です。")
    def download():
        return encode(add_grid_columns(frame,pair,np.arange(len(frame))))
    st.download_button("再生対象のグリッド判定CSV", data=download,
                       file_name=f"grid_replay_{'-'.join(map(str,active_seeds))}.csv",
                       mime="text/csv",on_click="ignore",key="grid_movie_csv")


def grid_view(run):
    st.subheader("集束グリッドによる選択的吸収")
    a,b,c=st.columns(3)
    with a:
        ratio=st.selectbox("グリッド比",RATIOS,index=1,format_func=lambda r:f"{r}:1",key="grid_ratio")
    with b:
        focus=st.number_input("集束距離 (cm)",min_value=70,max_value=180,value=100,step=1,key="grid_focus")
    with c:
        sid=st.number_input("比較用SID (cm)",min_value=96,max_value=180,value=100,step=1,key="grid_sid")
    grid=Grid(ratio,focus,sid)
    pair=session_projection(st.session_state,run,grid)
    st.caption(f"鉛箔は想定焦点へ向けて配置。グリッド比＝箔高さ {grid.height*10:.2f} mm ／"
               f"中間物質の幅 {GAP*10:.2f} mm。箔幅 {LEAD*10:.2f} mm。寸法と集束距離は検出器側の面を基準とします。")
    st.write(f"**同じ光子を比較**　シード {run.settings.seed}　·　全入射 {run.settings.count:,} 個")
    counts=pair.counts()
    for col,row,name in zip(st.columns(2),counts.itertuples(),("グリッドなし","グリッドあり")):
        pp,ss=row.primary_passed,row.scatter_passed
        fractions=arrival_share(pp,ss)
        col.metric(name+"：検出器面に到達",f"{pp+ss:,} 個")
        col.caption(f"一次 {pp:,} 個（{fractions[0]:.1%}）　／　散乱 {ss:,} 個（{fractions[1]:.1%}）"
                    if fractions else "到達0個のため割合は算出できません。")
    st.caption("割合の分母は各配置で検出器面に到達した光子数です。エネルギー付与量・検出器信号・空気カーマの割合ではありません。")
    with st.expander("全標本の内訳：入射・透過・鉛箔吸収・検出器面への到達"):
        metrics={"primary_incident":"一次線｜入口に入射", "scatter_incident":"散乱線｜入口に入射",
                 "primary_passed":"一次線｜出口を通過 ＝ 検出器面に到達",
                 "scatter_passed":"散乱線｜出口を通過 ＝ 検出器面に到達",
                 "primary_lead_absorbed":"一次線｜鉛箔で吸収","scatter_lead_absorbed":"散乱線｜鉛箔で吸収",
                 "side_exit":"側方退出（一次＋散乱）"}
        table=counts[list(metrics)].rename(columns=metrics).T
        table.columns=["グリッドなし (個)","グリッドあり (個)"]
        st.dataframe(table,width="stretch",column_config={"_index":"光子の判定"})
        st.caption("なしの列は同じ仮想入口・出口を使います。幅44 cmの側面から出た光子は到達数に含めません。")
    with st.expander("到達光子の方向分布（全標本）"):
        st.caption("0°は検出器面に垂直、左向きは負、右向きは正。保存した方向をx–z断面へ投影し、5°ごとに個数を数えます。"
                   "左右の縦軸は同一です。コンプトン散乱角θとは異なります。")
        st.plotly_chart(angle_figure(detector_distributions(run,pair)),key="arrival_angles",
                        width="stretch",theme=None,config={"displayModeBar":False,"scrollZoom":False})
    st.markdown("**グリッドなし／ありの同期再生**")
    limit=st.selectbox("グリッド再生の光子数（各シード）",PLAYBACK_LIMITS,index=3,key="grid_limit")
    grid_movie(run,grid,limit)
    initial=default_detail_id(pair)
    key=run.settings
    if st.session_state.get("_grid_detail_setup") != key:
        st.session_state["grid_photon"] = initial
        st.session_state["_grid_detail_setup"] = key
    with st.expander("全標本から光子番号を指定して鉛箔と交点を拡大"):
        number=st.number_input("比較する光子番号",min_value=1,max_value=run.settings.count,
                               step=1,key="grid_photon")
        index=number-1
        kind = "一次線" if pair.primary[index] else (
            f"{PARTS[run.part[index]]}からの散乱線" if pair.scattered[index] else ENERGY_NAMES[run.process[index]])
        st.write(f"光子 #{number}（{kind}）　｜　なし：{OUTCOMES[pair.without[index]]}　｜　あり：{OUTCOMES[pair.with_grid[index]]}")
        st.plotly_chart(comparison_figure(run,pair,index),key="grid_detail_plot",width="stretch",theme=None,
                        config={"displayModeBar":False,"scrollZoom":False})
        if pair.entered[index]:
            st.caption(f"局所 x=0 は入口位置 x={pair.entry_x[index]:.5f} cm。左右は同一尺度の断面です。"
                       "濃い帯が鉛箔、白いすき間が中間物質、青緑の横線が検出器面です。")
        else:
            st.caption("選択した光子は入口に入射しません。図は周辺部の箔の構造を示します。")
    with st.expander("比較条件と適用範囲"):
        st.write("線状グリッドのx–z断面で計算します。y方向には一様です。点焦点と被写体・撮影台の位置を固定し、"
                 "SIDは撮影台の下で検出器とグリッドを移動して変更します。基準計算の空気層は100 cmまでです。"
                 "仮想入口より手前に初回相互作用がなければ一次線として扱い、それ以降の空間は直線外挿します。")
        st.write("コンプトン散乱後は保存済みの方向を延長します。光電吸収は発生点で終了し、干渉性散乱は方向未計算です。"
                 "鉛箔は最初の接触で完全吸収、中間物質は完全透過と仮定します。再散乱・散乱後の減弱・実機の到達線量は計算対象外です。")
        st.write("散乱成分が減ると画像コントラストは改善し得ます。この版では幾何学的な光子数を表示します。")
        st.markdown("[集束グリッドの幾何学とカットオフの実験原著](https://pmc.ncbi.nlm.nih.gov/articles/PMC4034420/)")
    with st.expander("全標本のグリッド判定をCSV保存"):
        counts=counts.assign(grid_model=GRID_VERSION, seed=run.settings.seed, incident_photons=run.settings.count,
            energy_keV=run.settings.energy,object_cm=run.settings.thickness,field_cm=run.settings.field,
            grid_ratio=ratio,grid_focus_cm=focus,grid_sid_cm=sid)
        st.download_button("グリッド比較の集計CSV",data=encode(counts),file_name="grid_comparison.csv",
                           mime="text/csv",on_click="ignore",key="grid_summary_csv")
        st.download_button("全入射光子のグリッド判定CSV",data=partial(grid_csv,run,pair),
                           file_name=f"grid_all_s{run.settings.seed}.csv",mime="text/csv",on_click="ignore",
                           key="grid_all_csv")
