# 物質データ

`xcom.csv` はNIST XCOM（SRD 8）に各物質の元素質量分率を入力して得た質量相互作用係数（cm²/g）です。各行の順序は干渉性散乱、非干渉性散乱、光電吸収、干渉性散乱を含む全減弱です。密度（g/cm³）と元素質量分率はNISTの物質定義から取得し、`materials.json` に記録しました。[NIST XCOM](https://physics.nist.gov/PhysRefData/Xcom/html/xcom1.html) ／ [XCOMの計算方法](https://physics.nist.gov/PhysRefData/Xcom/Text/chap3.html)

| 材料 | 密度 (g/cm³) | NIST物質定義 | 原表取得日 |
|---|---:|---|---|
| 乾燥空気（海面付近） | 0.00120479 | [104](https://physics.nist.gov/cgi-bin/Star/compos.pl?matno=104) | 2026-11-12 |
| 液体水 | 1.000 | [276](https://physics.nist.gov/cgi-bin/Star/compos.pl?matno=276) | 2026-11-12 |
| アルミニウム | 2.6989 | [013](https://physics.nist.gov/cgi-bin/Star/compos.pl?matno=013) | 2026-11-12 |
| 鉛 | 11.35 | [082](https://physics.nist.gov/cgi-bin/Star/compos.pl?matno=082) | 2026-11-12 |
| ポリメタクリル酸メチル（PMMA） | 1.19 | [223](https://physics.nist.gov/cgi-bin/Star/compos.pl?matno=223) | 2026-11-13 |
| ポリカーボネート（PC） | 1.20 | [219](https://physics.nist.gov/cgi-bin/Star/compos.pl?matno=219) | 2026-11-13 |

使用する単色エネルギーは 30、40、50、60、70、80、85、90、100、120、150 keV の11点です。各値はXCOMの原表の値をそのまま格納しています。鉛のK吸収端は88.0045 keVで、前後の85、90 keVの全減弱係数はそれぞれ2.081、7.256 cm²/gです。アプリは原表の各点で計算し、吸収端をまたぐ補間を行いません。[NIST 鉛の吸収端](https://physics.nist.gov/PhysRefData/XrayMassCoef/ElemTab/z82.html)

全減弱と各部分係数は原表で別々に丸められています。今回の全66行で、部分係数の和と全減弱の相対差は最大0.044%です。相互作用までの距離には密度×全減弱を使い、相互作用が起きた場合の種類は各部分係数をその和で規格化して選びます。この範囲では電子対生成の列は0です。空気組成は原表の表示桁で質量分率の和が0.999999になり、XCOMは照会時に規格化します。

2026-11-13に、6物質×11エネルギー×4係数＝264値を照会応答のHTMLと別のパーサーで全数照合しました。さらに6物質すべての組成と係数をNISTから再取得し、再構築したCSV・JSONが配布ファイルとバイト単位で一致することを確認しました。再取得にはPythonとcurlを使用します。プロジェクトのルートから次を実行してください。保存済み応答を使う場合は `--fetch` を省きます。

```sh
python tools/rebuild_xcom.py --fetch --raw /tmp/scatter-nist-raw --out /tmp/scatter-nist-export
diff -u data/xcom.csv /tmp/scatter-nist-export/xcom.csv
diff -u data/materials.json /tmp/scatter-nist-export/materials.json
```
