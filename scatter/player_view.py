from functools import partial
from pathlib import Path

import streamlit as st

from .model import GROUPS
from .playback import MAX_SHOW, make_playlist, pools_for, selection_csv, selections

_ASSETS = Path(__file__).with_name("player")
def _asset(name):
    return (_ASSETS / name).read_text(encoding="utf-8")

_player = st.components.v2.component("vxsl_photon_film",
    html=_asset("panel.html"),css=_asset("panel.css"),
    js="\n".join(_asset(name) for name in ("clock.mjs", "history.mjs", "paired_ray.mjs", "room_camera.mjs",
                                           "detector_view.mjs", "screen.mjs")))


def playback_view(run, sources, limit, examples, close):
    st.markdown("**連続照射アニメーション**")
    mode = st.radio("再生する標本", ("固定シード", "シード連続（1 → 2 → 3）"),
                    horizontal=True,key="film_mode")
    sequence = mode.startswith("シード連続")
    groups = [GROUPS.index(s) for s in sources]
    pools = pools_for(st.session_state,run,sequence,capacity=MAX_SHOW)
    selected = selections(pools, limit, groups, examples, fill_ordered=True)
    if sequence:
        st.caption(f"独立した3標本を準備しました（各 {run.settings.count:,} 個）。1 → 2 → 3 の順は物理的な時間ではありません。"
                   f"上部の全体計数と「計数と分布」は引き続き照射条件のシード {run.settings.seed} の値です。")
    else:
        st.caption(f"照射条件のシード {run.settings.seed} の計算済み標本を使用します。")
    st.caption("再生速度は観察用で、実際の光子の飛行速度を表しません。コンプトン散乱後の矢印は方向を示す18 cmの模式表示です。"
               "光電吸収・干渉性散乱では発生点で追跡を終えます。")
    total = sum(len(ids) for _,ids in selected)
    detail = "　／　".join(f"シード {s.seed}：{len(ids)} 本" for s,ids in selected)
    st.markdown(f"**再生対象 {total} 本**　{detail}")
    if any(len(ids) < limit for _, ids in selected):
        st.caption(f"指定は各シード{limit}本です。この条件に該当する計算済みの光子を、実数分だけ再生します。")
    if not total:
        st.info("この条件で再生できる光子はありません。発生源または飛跡の選び方を変更してください。")
        return
    if sequence and any(not ids for _,ids in selected):
        st.caption("表示対象が0本のシードは読み飛ばします。")
    data=make_playlist(run,selected,close,limit,groups,examples,sequence)
    _player(key="vxsl_player",data=data)
    st.caption("累積飛跡は現在のシードで描いた光子の本数です。散乱線はコンプトン散乱後に描いた矢印を数えます。"
               "光電吸収・干渉性散乱・無相互作用の光子は一次線の飛跡だけを残します。"
               "全計算標本の発生源別計数は「計数と分布」で確認できます。")
    st.caption("再生済みは飛跡を最後まで描いた光子の通算です。発生点や光子番号を選ぶと一時停止し、"
               "選んだ光子を表示します。同じ光子は1回だけ数えます。拡大時も累積本数は全図を対象とします。"
               "シードが切り替わると図の蓄積を新しくし、「停止・先頭へ」で通算も消去します。")
    tag="s1-3" if sequence else f"s{run.settings.seed}"
    st.download_button("再生対象の光子をCSV保存",data=partial(selection_csv,selected),
                       file_name=f"scatter_replay_{tag}.csv",mime="text/csv",on_click="ignore",key="film_csv")
