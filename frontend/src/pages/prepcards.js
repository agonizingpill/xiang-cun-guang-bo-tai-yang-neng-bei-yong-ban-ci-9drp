        import {workspace} from '../workspace.js';
        import {el} from '../dom.js';

        const page = {
  "title": "晴阴备播卡",
  "module": "备播卡（晴阴两档）",
  "caption": "晴阴备播卡",
  "detail": "同一批复核读数一次拟合，晴阴分别预测，并以留出段同天气少算最多的电量做余量；没留出样本的天气不给领卡，开播只领现场天气那一档。",
  "path": "/prepcards",
  "columns": [
    {
      "name": "code",
      "label": "备播卡编号"
    },
    {
      "name": "airslot",
      "label": "节目时段"
    },
    {
      "name": "meter",
      "label": "电表"
    },
    {
      "name": "clear_wh",
      "label": "晴天需电 Wh"
    },
    {
      "name": "cloudy_wh",
      "label": "阴天需电 Wh"
    },
    {
      "name": "state",
      "label": "状态"
    },
    {
      "name": "claimed_weather",
      "label": "已领档位"
    },
    {
      "name": "claimed_wh",
      "label": "领卡电量 Wh"
    },
    {
      "name": "receipt",
      "label": "领用凭据"
    }
  ],
  "layout": "split",
  "view": "table",
  "actions": [
    {
      "name": "prepare_card",
      "label": "测算晴阴两档需电量",
      "path": "/prepcards/prepare",
      "fields": [
        {
          "name": "airslot",
          "label": "节目编号",
          "kind": "text",
          "initial": "AIR-17"
        },
        {
          "name": "meter",
          "label": "电表",
          "kind": "text",
          "initial": "BAT-04"
        }
      ],
      "help": "同一批审签读数同时预测晴天和阴天，余量取留出段同天气少算最多的电量；无留出样本的天气返回空值。",
      "roles": [
        "operator",
        "reviewer"
      ],
      "success": "已写入"
    },
    {
      "name": "issue_card",
      "label": "签发备播卡",
      "path": "/prepcards/issue",
      "fields": [
        {
          "name": "code",
          "label": "备播卡编号",
          "kind": "text",
          "initial": "PC-01"
        },
        {
          "name": "token",
          "label": "计算号",
          "kind": "token",
          "initial": ""
        }
      ],
      "help": "只够一种天气也可发卡，另一档显示为空且不能领用。",
      "roles": [
        "reviewer"
      ],
      "success": "已写入"
    },
    {
      "name": "claim_card",
      "label": "按现场天气领用",
      "path": "/prepcards/claim",
      "fields": [
        {
          "name": "card",
          "label": "备播卡编号",
          "kind": "text",
          "initial": "PC-01"
        },
        {
          "name": "receipt",
          "label": "领用凭据",
          "kind": "text",
          "initial": "RC-77"
        },
        {
          "name": "clear",
          "label": "现场晴天",
          "kind": "bool",
          "initial": true
        }
      ],
      "help": "只领现场天气且有留出让路的一档；同一凭据断线重试拿回原卡，不重复领卡。",
      "roles": [
        "operator",
        "reviewer"
      ],
      "success": "已写入"
    }
  ]
};

        export const {title} = page;
        export const key = "prepcards";
        export async function render(root, role) {
          await workspace(root, role, page);

        }
