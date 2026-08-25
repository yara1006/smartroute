import { defineConfig } from "vitepress";

export default defineConfig({
  title: "SmartRoute AI",
  description: "本地生活路线规划 Agent — 美团 AI 黑客松项目",
  lang: "zh-CN",

  themeConfig: {
    logo: "/logo.svg",

    nav: [
      { text: "指南", link: "/guide/getting-started" },
      { text: "API 参考", link: "/reference/api" },
      { text: "架构", link: "/reference/architecture" },
      {
        text: "相关链接",
        items: [
          { text: "GitHub", link: "https://github.com/yara1006/smartroute" },
          { text: "变更日志", link: "/changelog" },
        ],
      },
    ],

    sidebar: {
      "/guide/": [
        {
          text: "指南",
          items: [
            { text: "快速开始", link: "/guide/getting-started" },
            { text: "配置说明", link: "/guide/configuration" },
            { text: "部署", link: "/guide/deployment" },
          ],
        },
      ],
      "/reference/": [
        {
          text: "参考",
          items: [
            { text: "API 接口", link: "/reference/api" },
            { text: "架构说明", link: "/reference/architecture" },
            { text: "数据模型", link: "/reference/models" },
          ],
        },
      ],
    },

    socialLinks: [
      { icon: "github", link: "https://github.com/yara1006/smartroute" },
    ],

    footer: {
      message: "基于 MIT 协议开源",
      copyright: "Copyright © 2026 SmartRoute Team",
    },

    search: {
      provider: "local",
    },
  },
});
