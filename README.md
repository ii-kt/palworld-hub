# Palworld 日本語配合計算機

Palworld `v1.0.1.100619`（クライアントBuild `24181527`／サーバーBuild `24181105`）の固定ゲーム資産から生成した配合計算機です。

- 公開済みパル: 288形態
- 順序を区別しない親ペア: 41,616組
- 性別依存行を含む配合結果: 41,617行

## 検証

```bash
python tools/build_verified_dataset.py
python tools/audit_breeding_sources.py
python -m unittest -v tests.test_verified_dataset
npm ci
npm test
```

データの由来、照合範囲、未実施のゲーム内検証は、サイトおよび `evidence/README.md`、`audit/` の機械可読レポートに記録しています。

## 公開URL

<https://ii-kt.github.io/palworld-hub/>
