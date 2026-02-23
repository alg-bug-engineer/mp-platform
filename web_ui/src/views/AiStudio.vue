<template>
  <div class="studio-page">
    <section class="hero">
      <div>
        <h1>{{ pageTitle }}</h1>
        <p>{{ pageDesc }}</p>
      </div>
      <a-space wrap>
        <a-button @click="refreshAll" :loading="overviewLoading || loading">刷新数据</a-button>
        <a-button :type="isWechatAuthorized ? 'secondary' : 'primary'" :disabled="isWechatAuthorized" @click="openAuth">
          {{ isWechatAuthorized ? '已授权' : '扫码授权公众号' }}
        </a-button>
        <a-button type="outline" @click="goBilling">套餐订阅</a-button>
      </a-space>
    </section>

    <section class="studio-switcher">
      <a-space wrap>
        <a-button
          v-for="item in sectionTabs"
          :key="`section-${item.key}`"
          size="small"
          :type="item.key === activeSection ? 'primary' : 'outline'"
          @click="focusSection(item.key)"
        >
          {{ item.label }}
        </a-button>
      </a-space>
    </section>

    <div class="studio-layout" :class="{ 'draftbox-mode': isDraftboxRoute }">
      <aside v-if="!isDraftboxRoute" class="studio-tools">

        <div id="ai-profile-anchor"></div>
        <a-card title="AI 创作配置" class="panel">
          <a-form :model="profile" layout="vertical">
            <a-row :gutter="16">
              <a-col :xs="24" :md="12">
                <a-form-item label="Base URL">
                  <a-input v-model="profile.base_url" placeholder="https://api.moonshot.cn/v1" />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="12">
                <a-form-item label="模型名称">
                  <a-input v-model="profile.model_name" placeholder="kimi-k2-0711-preview" />
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="16">
              <a-col :xs="24" :md="12">
                <a-form-item label="API Key">
                  <a-input-password v-model="profile.api_key" placeholder="sk-..." />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="12">
                <a-form-item label="温度(0-100)">
                  <a-slider v-model="profile.temperature" :min="0" :max="100" :step="1" />
                </a-form-item>
              </a-col>
            </a-row>
            <a-space>
              <a-button type="primary" :loading="saving" @click="saveProfile">保存配置</a-button>
              <a-button @click="loadProfile">刷新配置</a-button>
            </a-space>
          </a-form>
        </a-card>

        <a-card class="panel" title="套餐与授权">
          <a-space direction="vertical" fill>
            <div class="plan-head">
              <a-tag :color="planTagColor">{{ overview.plan?.label || '免费用户' }}</a-tag>
              <span class="muted">{{ overview.plan?.price_hint || '' }}</span>
            </div>
            <div class="quota-line">
              <span>AI 配额</span>
              <span>{{ overview.plan?.ai_used || 0 }}/{{ overview.plan?.ai_quota || 0 }}</span>
            </div>
            <div class="quota-line">
              <span>图片配额</span>
              <span>{{ overview.plan?.image_used || 0 }}/{{ overview.plan?.image_quota || 0 }}</span>
            </div>
            <a-alert :type="overview.wechat_auth?.authorized ? 'success' : 'warning'">
              {{ overview.wechat_auth?.authorized ? '公众号已授权，可直接投递草稿' : '公众号未授权，暂只能保存在本地草稿箱' }}
            </a-alert>
            <a-space wrap>
              <a-button
                size="small"
                :type="isWechatAuthorized ? 'secondary' : 'outline'"
                :disabled="isWechatAuthorized"
                @click="openAuth"
              >
                {{ isWechatAuthorized ? '已授权' : '去授权' }}
              </a-button>
              <a-button size="small" type="primary" @click="goBilling">去套餐订阅页</a-button>
            </a-space>
          </a-space>
        </a-card>
      </aside>

      <section class="studio-display" :class="{ full: isDraftboxRoute }">
        <a-row :gutter="16" class="summary-row">
          <a-col :xs="24" :md="8">
            <a-card class="summary-card" :loading="overviewLoading">
              <template #title>创作额度</template>
              <a-space direction="vertical" fill>
                <div class="quota-line">
                  <span>AI 配额</span>
                  <span>{{ overview.plan?.ai_used || 0 }}/{{ overview.plan?.ai_quota || 0 }}</span>
                </div>
                <a-progress :percent="quotaPercent(overview.plan?.ai_used, overview.plan?.ai_quota)" />
                <div class="quota-line">
                  <span>图片配额</span>
                  <span>{{ overview.plan?.image_used || 0 }}/{{ overview.plan?.image_quota || 0 }}</span>
                </div>
                <a-progress :percent="quotaPercent(overview.plan?.image_used, overview.plan?.image_quota)" status="success" />
                <a-button size="small" type="outline" @click="goBilling">升级套餐能力</a-button>
              </a-space>
            </a-card>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-card class="summary-card" :loading="overviewLoading">
              <template #title>公众号连接状态</template>
              <a-space direction="vertical" fill>
                <a-alert :type="overview.wechat_auth?.authorized ? 'success' : 'warning'">
                  {{ overview.wechat_auth?.authorized ? '已授权，可投递公众号草稿箱' : '未授权，仅可保存本地草稿箱' }}
                </a-alert>
                <div class="quota-line">
                  <span>草稿箱投递能力</span>
                  <span>{{ overview.plan?.can_publish_wechat_draft ? '已开通' : '套餐未开通' }}</span>
                </div>
                <a-button
                  size="small"
                  :type="isWechatAuthorized ? 'secondary' : 'outline'"
                  :disabled="isWechatAuthorized"
                  @click="openAuth"
                >
                  {{ isWechatAuthorized ? '已授权' : '去授权' }}
                </a-button>
              </a-space>
            </a-card>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-card class="summary-card" :loading="overviewLoading">
              <template #title>内容资产</template>
              <a-row :gutter="8">
                <a-col :span="6">
                  <div class="metric">
                    <div class="value">{{ overview.stats?.mp_count || 0 }}</div>
                    <div class="label">公众号</div>
                  </div>
                </a-col>
                <a-col :span="6">
                  <div class="metric">
                    <div class="value">{{ overview.stats?.article_count || 0 }}</div>
                    <div class="label">文章</div>
                  </div>
                </a-col>
                <a-col :span="6">
                  <div class="metric">
                    <div class="value">{{ overview.stats?.local_draft_count || 0 }}</div>
                    <div class="label">草稿</div>
                  </div>
                </a-col>
                <a-col :span="6">
                  <div class="metric">
                    <div class="value">{{ overview.stats?.pending_publish_count || 0 }}</div>
                    <div class="label">待投递</div>
                  </div>
                </a-col>
              </a-row>
            </a-card>
          </a-col>
        </a-row>

        <a-card v-if="activeSection === 'workbench'" class="panel" title="近 7 天运营指标" :loading="overviewLoading">
          <a-row :gutter="12" class="activity-metrics">
            <a-col :xs="12" :md="6">
              <div class="activity-metric">
                <div class="activity-value">{{ overview.activity?.draft_count_7d || 0 }}</div>
                <div class="activity-label">7天创作稿件</div>
              </div>
            </a-col>
            <a-col :xs="12" :md="6">
              <div class="activity-metric">
                <div class="activity-value">{{ overview.activity?.avg_daily_draft || 0 }}</div>
                <div class="activity-label">日均稿件</div>
              </div>
            </a-col>
            <a-col :xs="12" :md="6">
              <div class="activity-metric">
                <div class="activity-value">{{ activitySuccessRateText }}</div>
                <div class="activity-label">投递成功率</div>
              </div>
            </a-col>
            <a-col :xs="12" :md="6">
              <div class="activity-metric">
                <div class="activity-value">{{ overview.activity?.publish_failed_7d || 0 }}</div>
                <div class="activity-label">投递失败数</div>
              </div>
            </a-col>
          </a-row>

          <div class="activity-trend">
            <div v-for="item in activityTrend" :key="`trend-${item.date}`" class="activity-item">
              <div class="activity-date">{{ item.date.slice(5) }}</div>
              <div class="activity-bar-row">
                <span class="bar-name">稿</span>
                <div class="bar-track">
                  <div class="bar-fill draft" :style="{ width: `${activityDraftPercent(item.drafts)}%` }"></div>
                </div>
                <span class="bar-value">{{ item.drafts }}</span>
              </div>
              <div class="activity-bar-row">
                <span class="bar-name">成</span>
                <div class="bar-track">
                  <div class="bar-fill success" :style="{ width: `${activitySuccessPercent(item.publish_success)}%` }"></div>
                </div>
                <span class="bar-value">{{ item.publish_success }}</span>
              </div>
            </div>
          </div>
          <div class="muted">稿 = 当日新增草稿；成 = 当日成功投递到公众号草稿箱</div>
        </a-card>

        <a-card v-if="activeSection === 'workbench'" id="studio-workbench-card" title="内容创作工作台" class="panel">
          <a-space class="workbench-toolbar" style="margin-bottom: 12px; width: 100%;" wrap>
            <a-select v-model="activeMpId" placeholder="筛选公众号" allow-clear style="width: 220px;" @change="fetchArticles">
              <a-option v-for="mp in mps" :key="mp.id" :value="mp.id">{{ mp.name }}</a-option>
            </a-select>
            <a-input-search v-model="searchText" placeholder="搜索文章标题" style="width: 280px;" @search="fetchArticles" />
            <a-button @click="fetchArticles" :loading="loading">刷新列表</a-button>
            <a-button @click="resetFilters">清空筛选</a-button>
          </a-space>

          <div class="quick-chip-row">
            <span class="muted">快速平台</span>
            <a-button
              v-for="item in composePlatforms"
              :key="`chip-${item.key}`"
              size="mini"
              :type="createForm.platform === item.key ? 'primary' : 'outline'"
              @click="createForm.platform = item.key"
            >
              {{ item.label }}
            </a-button>
          </div>

          <a-textarea
            v-model="quickInstruction"
            placeholder="全局补充要求（可选），例如：更像真实作者口吻，避免模板化表达"
            :auto-size="{ minRows: 2, maxRows: 4 }"
          />

          <a-table
            :columns="columns"
            :data="articles"
            :loading="loading"
            :pagination="pagination"
            :row-class="articleRowClass"
            @page-change="onPageChange"
            style="margin-top: 12px;"
          >
            <template #titleCell="{ record }">
              <a-link @click="openArticle(record.id)">{{ record.title }}</a-link>
            </template>

            <template #tagsCell="{ record }">
              <a-space wrap>
                <a-tag v-for="tag in tagMap[record.id] || []" :key="`${record.id}-${tag}`" color="arcoblue">
                  {{ tag }}
                </a-tag>
                <span v-if="!(tagMap[record.id] || []).length" class="muted">-</span>
              </a-space>
            </template>

            <template #actions="{ record }">
              <a-space>
                <a-button type="text" :loading="runningKey === `analyze:${record.id}`" @click="runTask('analyze', record)">分析</a-button>
                <a-button type="text" :loading="runningKey === `create:${record.id}`" @click="openCreate(record)">创作</a-button>
                <a-button type="text" :loading="runningKey === `rewrite:${record.id}`" @click="runTask('rewrite', record)">仿写</a-button>
              </a-space>
            </template>
          </a-table>
        </a-card>

        <a-card v-if="activeSection === 'drafts'" id="studio-drafts-card" title="草稿历史（本地草稿箱）" class="panel" :loading="draftLoading">
          <a-list :data="drafts">
            <template #item="{ item }">
              <a-list-item :id="`draft-item-${item.id}`" :class="{ 'active-draft-item': item.id === activeDraftId }">
                <div style="width: 100%;">
                  <div class="draft-head">
                    <a-link @click="openDraftDetail(item)">{{ item.title }}</a-link>
                    <span class="muted">{{ item.created_at }}</span>
                  </div>
                  <div class="muted">文章ID：{{ item.article_id }} | 平台：{{ item.platform }}</div>
                </div>
              </a-list-item>
            </template>
          </a-list>
        </a-card>

        <a-card v-if="activeSection === 'queue'" id="studio-queue-card" title="草稿投递队列（公众号）" class="panel" :loading="queueLoading">
          <a-space style="margin-bottom: 10px;">
            <a-button @click="fetchPublishQueue" :loading="queueLoading">刷新队列</a-button>
            <a-button type="primary" @click="runProcessQueue" :loading="processingQueue">处理待投递任务</a-button>
          </a-space>
          <a-table :columns="queueColumns" :data="publishQueue" :pagination="false">
            <template #statusCell="{ record }">
              <a-tag :color="queueStatusColor(record.status)">{{ record.status }}</a-tag>
            </template>
            <template #actionCell="{ record }">
              <a-space>
                <a-button size="mini" @click="retryQueueTask(record.id)">立即重试</a-button>
                <a-button size="mini" status="danger" @click="deleteQueueTask(record)">删除</a-button>
              </a-space>
            </template>
          </a-table>
        </a-card>
      </section>
    </div>

    <a-modal v-model:visible="createVisible" title="图文创作设置" width="900px" :mask-closable="false" @ok="submitCreate">
      <a-form :model="createForm" layout="vertical">
        <a-form-item label="发布平台" class="platform-form-item">
          <div class="platform-grid">
            <label
              v-for="item in composePlatforms"
              :key="item.key"
              class="platform-item"
              :class="{ active: createForm.platform === item.key }"
            >
              <input type="radio" :value="item.key" v-model="createForm.platform" />
              <img :src="platformLogo(item.key)" :alt="item.label" />
              <div class="platform-name">{{ item.label }}</div>
              <div class="platform-desc">{{ item.style }}</div>
            </label>
          </div>
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="写作风格">
              <a-select v-model="createForm.style" allow-clear>
                <a-option v-for="s in composeStyles" :key="s.key" :value="s.key">{{ s.label }}</a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="篇幅">
              <a-select v-model="createForm.length" allow-clear>
                <a-option v-for="l in composeLengths" :key="l.key" :value="l.key">{{ l.label }}</a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="图片张数">
              <a-input-number v-model="createForm.image_count" :min="0" :max="9" style="width: 100%;" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="目标受众（可选)">
              <a-input v-model="createForm.audience" placeholder="例如：35 岁以下科技行业从业者" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="语气（可选)">
              <a-input v-model="createForm.tone" placeholder="例如：真实克制、专业不端着" />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="补充要求（可选)">
          <a-textarea v-model="createForm.instruction" :auto-size="{ minRows: 3, maxRows: 6 }" />
        </a-form-item>

        <a-form-item label="图片生成（即梦）">
          <a-switch v-model="createForm.generate_images" />
          <span class="muted" style="margin-left: 8px;">生图能力由平台统一加载，不需要用户单独配置；服务不可用时会自动降级为配图提示词。</span>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="resultVisible" :title="resultTitle" :footer="false" width="980px">
      <a-space direction="vertical" style="width: 100%;">
        <a-space wrap>
          <a-button @click="copyResult">复制结果文本</a-button>
          <a-button type="primary" @click="openPublish">发布到草稿箱</a-button>
          <a-tag color="arcoblue">{{ overview.plan?.label || '' }}</a-tag>
        </a-space>

        <a-space wrap>
          <a-tag v-for="tag in (resultData.recommended_tags || [])" :key="`result-${tag}`" color="green">{{ tag }}</a-tag>
        </a-space>

        <a-alert v-if="resultData.image_notice" type="info">{{ resultData.image_notice }}</a-alert>

        <div v-if="(resultData.images || []).length" class="image-grid">
          <a-card v-for="(img, idx) in resultData.images" :key="`img-${idx}`" size="small" class="image-card">
            <img :src="img" :alt="`image-${idx}`" class="gen-image" />
            <a-link :href="img" target="_blank">打开原图</a-link>
          </a-card>
        </div>

        <a-collapse v-if="(resultData.image_prompts || []).length">
          <a-collapse-item key="p" header="配图提示词">
            <ol>
              <li v-for="(p, i) in resultData.image_prompts" :key="`p-${i}`">{{ p }}</li>
            </ol>
          </a-collapse-item>
        </a-collapse>

        <a-typography-paragraph style="white-space: pre-wrap;">{{ resultData.result || '' }}</a-typography-paragraph>
      </a-space>
    </a-modal>

    <a-modal v-model:visible="publishVisible" title="发布公众号草稿箱" width="760px" :on-before-ok="submitPublish">
      <a-form :model="publishForm" layout="vertical">
        <a-form-item label="标题">
          <a-input v-model="publishForm.title" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="作者（可选）">
              <a-input v-model="publishForm.author" placeholder="默认空" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="摘要（可选）">
              <a-input v-model="publishForm.digest" placeholder="建议 80 字内" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="封面图链接（可选）">
          <a-input v-model="publishForm.cover_url" placeholder="https://..." />
        </a-form-item>
        <a-form-item label="同步公众号草稿箱">
          <a-switch v-model="publishForm.sync_to_wechat" />
          <span class="muted" style="margin-left: 8px;">关闭后只保存本地草稿箱</span>
        </a-form-item>
        <a-form-item label="失败自动进入重试队列">
          <a-switch v-model="publishForm.queue_on_fail" />
        </a-form-item>
        <a-form-item label="最大重试次数">
          <a-input-number v-model="publishForm.max_retries" :min="1" :max="8" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="draftDetailVisible" title="草稿详情" :footer="false" width="980px">
      <a-space direction="vertical" style="width: 100%;">
        <div class="draft-head">
          <strong>{{ currentDraft?.title || '-' }}</strong>
          <span class="muted">{{ currentDraft?.created_at || '' }}</span>
        </div>
        <div class="muted">
          文章ID：{{ currentDraft?.article_id || '-' }} | 平台：{{ currentDraft?.platform || '-' }} | 模式：{{ currentDraft?.mode || '-' }}
        </div>
        <a-space wrap>
          <a-button size="small" @click="copyCurrentDraft">复制草稿</a-button>
          <a-button size="small" @click="toggleDraftEdit">{{ draftEditing ? '取消编辑' : '编辑草稿' }}</a-button>
          <a-button v-if="draftEditing" size="small" type="primary" :loading="draftSaving" @click="saveCurrentDraft">保存修改</a-button>
          <a-button size="small" type="outline" :loading="draftSyncing" @click="openDraftSync">同步到公众号草稿箱</a-button>
          <a-button size="small" status="danger" :loading="draftDeleting" @click="removeCurrentDraft">删除草稿</a-button>
        </a-space>
        <a-divider style="margin: 8px 0;" />
        <template v-if="draftEditing">
          <a-form layout="vertical">
            <a-form-item label="草稿标题">
              <a-input v-model="draftEditForm.title" placeholder="请输入草稿标题" />
            </a-form-item>
            <a-form-item label="草稿内容">
              <a-textarea v-model="draftEditForm.content" :auto-size="{ minRows: 12, maxRows: 24 }" />
            </a-form-item>
          </a-form>
        </template>
        <a-typography-paragraph v-else style="white-space: pre-wrap; line-height: 1.75;">
          {{ currentDraft?.content || '暂无内容' }}
        </a-typography-paragraph>
      </a-space>
    </a-modal>

    <a-modal v-model:visible="draftSyncVisible" title="同步草稿到公众号" width="760px" :on-before-ok="submitDraftSync">
      <a-form :model="draftSyncForm" layout="vertical">
        <a-form-item label="同步目标">
          <a-select v-model="draftSyncForm.platform">
            <a-option value="wechat">微信公众号草稿箱</a-option>
          </a-select>
        </a-form-item>
        <a-form-item label="标题">
          <a-input v-model="draftSyncForm.title" />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="作者（可选）">
              <a-input v-model="draftSyncForm.author" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="摘要（可选）">
              <a-input v-model="draftSyncForm.digest" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="封面图链接（可选）">
          <a-input v-model="draftSyncForm.cover_url" placeholder="https://..." />
        </a-form-item>
        <a-form-item label="失败自动进入重试队列">
          <a-switch v-model="draftSyncForm.queue_on_fail" />
        </a-form-item>
        <a-form-item label="最大重试次数">
          <a-input-number v-model="draftSyncForm.max_retries" :min="1" :max="8" />
        </a-form-item>
        <a-alert type="info">
          如需公众号同步，请先确认平台出口 IP 已加入公众号后台白名单。
          <a-link style="margin-left: 8px;" @click="openWhitelistReminder(true)">查看白名单指引</a-link>
        </a-alert>
      </a-form>
    </a-modal>

    <a-modal
      v-model:visible="whitelistReminderVisible"
      title="公众号同步白名单提示"
      width="760px"
      :footer="false"
      @cancel="closeWhitelistReminderLocal"
    >
      <a-space direction="vertical" style="width: 100%;">
        <a-alert type="warning">
          为保证“同步到微信公众号草稿箱”可用，请先在微信公众平台配置 IP 白名单。
        </a-alert>
        <div>
          <strong>平台出口 IP：</strong>
          <div class="whitelist-ip-list">
            <a-tag v-for="ip in whitelistIps" :key="`whitelist-${ip}`" color="arcoblue">{{ ip }}</a-tag>
            <span v-if="!whitelistIps.length" class="muted">暂未配置，请联系平台管理员设置 WECHAT_WHITELIST_IPS</span>
          </div>
        </div>
        <div class="muted">{{ whitelistGuide }}</div>
        <a-link :href="whitelistDocUrl" target="_blank">打开公众号后台（白名单设置）</a-link>
        <a-space>
          <a-button @click="closeWhitelistReminderLocal">仅本地关闭</a-button>
          <a-button type="primary" status="warning" @click="closeWhitelistReminderForever">永远不再提示</a-button>
        </a-space>
      </a-space>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getAIProfile,
  updateAIProfile,
  aiAnalyze,
  aiCreate,
  aiRewrite,
  getComposeOptions,
  recommendTags,
  getWorkbenchOverview,
  getDrafts,
  updateDraft,
  deleteDraft,
  syncDraftToWechat,
  publishDraft,
  getPublishTasks,
  processPublishTasks,
  retryPublishTask,
  deletePublishTask,
  type AIComposeResult,
  type DraftRecord,
  type PublishTask,
} from '@/api/ai'
import { getArticles } from '@/api/article'
import { getSubscriptions } from '@/api/subscription'

import logoWechat from '@/assets/platform/wechat.svg'
import logoXhs from '@/assets/platform/xiaohongshu.svg'
import logoZhihu from '@/assets/platform/zhihu.svg'
import logoTwitter from '@/assets/platform/twitter.svg'

type StudioSection = 'workbench' | 'drafts' | 'queue'
type SectionTab = {
  key: StudioSection
  label: string
}
type ResultSnapshot = {
  title: string
  sourceTitle: string
  data: AIComposeResult
}

const RESULT_CACHE_PREFIX = 'studio:result:'
const WECHAT_WHITELIST_REMINDER_NEVER_KEY = 'studio:wechat-whitelist-reminder:never'

const showAuthQrcode = inject<() => void>('showAuthQrcode')
const globalWxAuthReady = inject<{ value: boolean } | null>('wxAuthReady', null)
const route = useRoute()
const router = useRouter()

const profile = reactive({
  base_url: 'https://api.moonshot.cn/v1',
  model_name: 'kimi-k2-0711-preview',
  api_key: '',
  temperature: 70,
})

const overviewLoading = ref(false)
const draftLoading = ref(false)
const queueLoading = ref(false)
const processingQueue = ref(false)
const saving = ref(false)
const loading = ref(false)
const runningKey = ref('')

const overview = reactive<any>({
  plan: null,
  stats: {},
  activity: { trend: [] },
  wechat_auth: {},
  wechat_whitelist: {},
  recent_drafts: [],
})

const drafts = ref<DraftRecord[]>([])
const publishQueue = ref<PublishTask[]>([])
const articles = ref<any[]>([])
const mps = ref<any[]>([])
const activeMpId = ref('')
const searchText = ref('')
const quickInstruction = ref('')
const resultSourceTitle = ref('')

const tagMap = reactive<Record<string, string[]>>({})
const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
})

const composePlatforms = ref<Array<{ key: string; label: string; style: string; structure: string }>>([])
const composeStyles = ref<Array<{ key: string; label: string; desc: string }>>([])
const composeLengths = ref<Array<{ key: string; label: string }>>([])

const createVisible = ref(false)
const draftDetailVisible = ref(false)
const draftSyncVisible = ref(false)
const whitelistReminderVisible = ref(false)
const whitelistReminderSessionClosed = ref(false)
const whitelistReminderNever = ref(localStorage.getItem(WECHAT_WHITELIST_REMINDER_NEVER_KEY) === '1')
const currentCreateArticle = ref<any>(null)
const currentDraft = ref<DraftRecord | null>(null)
const draftEditing = ref(false)
const draftSaving = ref(false)
const draftDeleting = ref(false)
const draftSyncing = ref(false)
const draftEditForm = reactive({
  title: '',
  content: '',
})
const draftSyncForm = reactive({
  platform: 'wechat',
  title: '',
  author: '',
  digest: '',
  cover_url: '',
  queue_on_fail: true,
  max_retries: 3,
})
const createForm = reactive({
  platform: 'wechat',
  style: '专业深度',
  length: 'medium',
  image_count: 1,
  audience: '',
  tone: '',
  instruction: '',
  generate_images: true,
})

const resultVisible = ref(false)
const resultTitle = ref('创作结果')
const resultData = reactive<AIComposeResult>({
  article_id: '',
  mode: 'create',
  result: '',
  recommended_tags: [],
  image_prompts: [],
  images: [],
  image_notice: '',
})

const publishVisible = ref(false)
const publishLoading = ref(false)
const publishForm = reactive({
  title: '',
  author: '',
  digest: '',
  cover_url: '',
  sync_to_wechat: true,
  queue_on_fail: true,
  max_retries: 3,
})

const getQueryText = (key: string) => {
  const value = route.query[key]
  return Array.isArray(value) ? String(value[0] || '') : String(value || '')
}

const parseQueryPage = () => {
  const value = Number(getQueryText('page') || 1)
  return Number.isFinite(value) && value > 0 ? value : 1
}

const isDraftboxRoute = computed(() => route.path.startsWith('/workspace/draftbox'))
const activeArticleId = computed(() => getQueryText('article_id'))
const activeModeFromQuery = computed(() => getQueryText('mode'))
const activeDraftId = computed(() => getQueryText('draft_id'))
const pageTitle = computed(() => (isDraftboxRoute.value ? '草稿箱' : '创作中台'))
const pageDesc = computed(() =>
  isDraftboxRoute.value
    ? '本地草稿管理与公众号投递队列分离展示，减少页面干扰。'
    : '将创作工作台、草稿管理和投递队列拆分为子页面，提高操作聚焦度。'
)
const activeSection = computed<StudioSection>(() => {
  const section = getQueryText('section').trim().toLowerCase()
  if (section === 'queue') return 'queue'
  if (section === 'drafts' || activeDraftId.value || isDraftboxRoute.value) return 'drafts'
  return 'workbench'
})
const sectionTabs = computed<SectionTab[]>(() => {
  if (isDraftboxRoute.value) {
    return [
      { key: 'drafts', label: '本地草稿' },
      { key: 'queue', label: '投递队列' },
    ]
  }
  return [
    { key: 'workbench', label: '创作工作台' },
    { key: 'drafts', label: '本地草稿' },
    { key: 'queue', label: '投递队列' },
  ]
})

const planTagColor = computed(() => {
  const tier = overview.plan?.tier || 'free'
  if (tier === 'premium') return 'purple'
  if (tier === 'pro') return 'arcoblue'
  return 'gray'
})
const isWechatAuthorized = computed(() => !!overview.wechat_auth?.authorized || !!globalWxAuthReady?.value)
const whitelistIps = computed<string[]>(() => {
  const raw = overview.wechat_whitelist?.ips
  if (!Array.isArray(raw)) return []
  return raw.map((item: any) => String(item || '').trim()).filter(Boolean)
})
const whitelistGuide = computed(() =>
  String(
    overview.wechat_whitelist?.guide ||
      '请在微信公众平台后台将平台出口 IP 加入白名单后，再执行公众号草稿箱同步。'
  )
)
const whitelistDocUrl = computed(() =>
  String(overview.wechat_whitelist?.doc_url || 'https://mp.weixin.qq.com/')
)

const activityTrend = computed(() => overview.activity?.trend || [])
const activitySuccessRateText = computed(() => {
  const value = Number(overview.activity?.publish_success_rate_7d)
  return Number.isFinite(value) ? `${value.toFixed(2)}%` : '--'
})
const activityDraftMax = computed(() =>
  Math.max(1, ...activityTrend.value.map((item: any) => Number(item?.drafts || 0)))
)
const activitySuccessMax = computed(() =>
  Math.max(1, ...activityTrend.value.map((item: any) => Number(item?.publish_success || 0)))
)
const activityDraftPercent = (value: number) => {
  const count = Math.max(0, Number(value || 0))
  if (!count) return 0
  return Math.max(8, Math.round((count / activityDraftMax.value) * 100))
}
const activitySuccessPercent = (value: number) => {
  const count = Math.max(0, Number(value || 0))
  if (!count) return 0
  return Math.max(8, Math.round((count / activitySuccessMax.value) * 100))
}

const columns = [
  { title: '标题', dataIndex: 'title', slotName: 'titleCell', ellipsis: true },
  { title: '推荐标签', dataIndex: 'tags', slotName: 'tagsCell', width: 240 },
  { title: '公众号', dataIndex: 'mp_name', width: 180, ellipsis: true },
  { title: '发布时间', dataIndex: 'created_at', width: 200 },
  { title: '操作', slotName: 'actions', width: 240 },
]

const queueColumns = [
  { title: '标题', dataIndex: 'title', ellipsis: true },
  { title: '状态', dataIndex: 'status', slotName: 'statusCell', width: 120 },
  { title: '重试', dataIndex: 'retries', width: 120, render: ({ record }: any) => `${record.retries || 0}/${record.max_retries || 0}` },
  { title: '下次重试', dataIndex: 'next_retry_at', width: 220 },
  { title: '错误信息', dataIndex: 'last_error', ellipsis: true },
  { title: '操作', slotName: 'actionCell', width: 200 },
]

const quotaPercent = (used: number = 0, quota: number = 1) => {
  const q = Math.max(1, Number(quota || 1))
  const u = Math.max(0, Number(used || 0))
  return Math.min(1, Number((u / q).toFixed(4)))
}

const platformLogo = (key: string) => {
  if (key === 'wechat') return logoWechat
  if (key === 'xiaohongshu') return logoXhs
  if (key === 'zhihu') return logoZhihu
  if (key === 'twitter') return logoTwitter
  return logoWechat
}

const openAuth = () => {
  if (isWechatAuthorized.value) {
    Message.success('公众号已授权')
    return
  }
  showAuthQrcode?.()
}

const goBilling = () => {
  router.push('/workspace/billing')
}

const shouldShowWhitelistReminder = () => {
  return !whitelistReminderNever.value && !whitelistReminderSessionClosed.value
}

const openWhitelistReminder = (force: boolean = false) => {
  if (!force && !shouldShowWhitelistReminder()) return
  whitelistReminderVisible.value = true
}

const closeWhitelistReminderLocal = () => {
  whitelistReminderSessionClosed.value = true
  whitelistReminderVisible.value = false
}

const closeWhitelistReminderForever = () => {
  whitelistReminderNever.value = true
  whitelistReminderSessionClosed.value = true
  whitelistReminderVisible.value = false
  localStorage.setItem(WECHAT_WHITELIST_REMINDER_NEVER_KEY, '1')
}

const setStudioQuery = (
  patch: Record<string, string | undefined>,
  mode: 'replace' | 'push' = 'replace'
) => {
  const nextQuery: Record<string, any> = { ...route.query }
  Object.keys(patch).forEach((key) => {
    const value = (patch[key] || '').trim()
    if (value) nextQuery[key] = value
    else delete nextQuery[key]
  })
  if (JSON.stringify(nextQuery) === JSON.stringify(route.query)) return
  if (mode === 'push') {
    router.push({ path: route.path, query: nextQuery })
    return
  }
  router.replace({ path: route.path, query: nextQuery })
}

const initFiltersFromQuery = () => {
  activeMpId.value = getQueryText('mp_id')
  searchText.value = getQueryText('search')
  pagination.current = parseQueryPage()
}

const scrollToAIConfig = () => {
  const el = document.getElementById('ai-profile-anchor')
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const handleActionableError = (error: any) => {
  const msg = String(error || '操作失败')
  if (msg.includes('API Key') || msg.includes('AI 配置')) {
    Modal.confirm({
      title: '需要先配置 AI Key',
      content: '请先在「AI 创作配置」中填写并保存 API Key，再重新执行。',
      okText: '去配置',
      hideCancel: false,
      onOk: () => scrollToAIConfig(),
    })
    return
  }
  if (msg.includes('公众号') && msg.includes('授权')) {
    Modal.confirm({
      title: '公众号尚未授权',
      content: '如需草稿投递，请先完成公众号扫码授权。',
      okText: isWechatAuthorized.value ? '已授权' : '去授权',
      hideCancel: false,
      onOk: () => {
        if (!isWechatAuthorized.value) openAuth()
      },
    })
    return
  }
  if (msg.toLowerCase().includes('access denied') || msg.toLowerCase().includes('jimeng')) {
    Modal.confirm({
      title: '生图服务暂不可用',
      content: '当前平台生图服务暂时不可用，可先继续创作，系统会返回配图提示词。',
      okText: '知道了',
      cancelText: '关闭',
      hideCancel: false,
      onOk: () => {},
    })
    return
  }
  Message.error(msg)
}

const openArticle = (id: string) => {
  window.open(`/views/article/${id}?auto_fetch=1`, '_blank')
}

const loadProfile = async () => {
  const data = await getAIProfile()
  profile.base_url = data.base_url || profile.base_url
  profile.model_name = data.model_name || profile.model_name
  profile.temperature = data.temperature ?? profile.temperature
  profile.api_key = ''
}

const saveProfile = async () => {
  try {
    saving.value = true
    await updateAIProfile({
      base_url: profile.base_url,
      model_name: profile.model_name,
      api_key: profile.api_key,
      temperature: profile.temperature,
    })
    Message.success('AI 配置已保存')
    profile.api_key = ''
  } finally {
    saving.value = false
  }
}

const loadComposeMeta = async () => {
  const data = await getComposeOptions()
  composePlatforms.value = data.platforms || []
  composeStyles.value = data.styles || []
  composeLengths.value = data.lengths || []
  if (composePlatforms.value.length && !composePlatforms.value.find((x) => x.key === createForm.platform)) {
    createForm.platform = composePlatforms.value[0].key
  }
}

const refreshOverview = async () => {
  overviewLoading.value = true
  try {
    const data = await getWorkbenchOverview()
    overview.plan = data.plan
    overview.stats = data.stats || {}
    overview.activity = data.activity || { trend: [] }
    overview.wechat_auth = data.wechat_auth || {}
    overview.wechat_whitelist = data.wechat_whitelist || {}
    overview.recent_drafts = data.recent_drafts || []
  } finally {
    overviewLoading.value = false
  }
}

const fetchDrafts = async () => {
  draftLoading.value = true
  try {
    drafts.value = await getDrafts(30)
    if (activeDraftId.value) {
      nextTick(() => scrollToActiveDraft('auto'))
    }
  } finally {
    draftLoading.value = false
  }
}

const queueStatusColor = (status: string) => {
  if (status === 'success') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'processing') return 'arcoblue'
  return 'orange'
}

const fetchPublishQueue = async () => {
  queueLoading.value = true
  try {
    publishQueue.value = await getPublishTasks({ limit: 50 })
  } finally {
    queueLoading.value = false
  }
}

const runProcessQueue = async () => {
  processingQueue.value = true
  try {
    const data = await processPublishTasks(20)
    Message.info(`队列处理完成：成功 ${data.success}，失败 ${data.failed}`)
    await fetchPublishQueue()
    await refreshOverview()
  } finally {
    processingQueue.value = false
  }
}

const retryQueueTask = async (taskId: string) => {
  const data = await retryPublishTask(taskId)
  Message.info(data.message || '重试请求已发送')
  await fetchPublishQueue()
}

const deleteQueueTask = async (record: PublishTask) => {
  const taskId = String(record?.id || '').trim()
  if (!taskId) return
  Modal.confirm({
    title: '删除投递任务',
    content: `确认删除任务「${record?.title || taskId}」吗？`,
    okText: '删除',
    cancelText: '取消',
    onOk: async () => {
      await deletePublishTask(taskId)
      Message.success('任务已删除')
      await fetchPublishQueue()
      await refreshOverview()
    },
  })
}

const fetchMps = async () => {
  const res = await getSubscriptions({ page: 0, pageSize: 100 } as any)
  mps.value = (res.list || []).map((item: any) => ({
    id: item.id,
    name: item.mp_name || item.name,
  }))
}

const fetchArticleTags = async () => {
  const payload = articles.value.map((item: any) => ({ article_id: item.id, title: item.title }))
  if (!payload.length) return
  const data = await recommendTags(payload, 6)
  Object.keys(tagMap).forEach((k) => delete tagMap[k])
  ;(data || []).forEach((item: any) => {
    tagMap[item.article_id] = item.tags || []
  })
}

const fetchArticles = async (syncQuery: boolean = true) => {
  try {
    loading.value = true
    const res = await getArticles({
      page: pagination.current - 1,
      pageSize: pagination.pageSize,
      search: searchText.value,
      mp_id: activeMpId.value,
    } as any)
    articles.value = res.list || []
    pagination.total = res.total || 0
    if (syncQuery) {
      setStudioQuery({
        mp_id: activeMpId.value || undefined,
        search: searchText.value || undefined,
        page: String(pagination.current || 1),
      })
    }
    await fetchArticleTags()
  } finally {
    loading.value = false
  }
}

const resetFilters = async () => {
  activeMpId.value = ''
  searchText.value = ''
  pagination.current = 1
  await fetchArticles()
}

const focusSection = (section: StudioSection) => {
  setStudioQuery({
    section: section === 'workbench' ? undefined : section,
    draft_id: section === 'drafts' ? activeDraftId.value || undefined : undefined,
  }, 'push')
}

const openDraftDetail = (draft: DraftRecord, syncQuery: boolean = true) => {
  if (!draft) return
  currentDraft.value = draft
  draftEditing.value = false
  draftEditForm.title = draft.title || ''
  draftEditForm.content = draft.content || ''
  const metadata = (draft.metadata || {}) as Record<string, any>
  draftSyncForm.platform = 'wechat'
  draftSyncForm.title = draft.title || ''
  draftSyncForm.author = String(metadata.author || '')
  draftSyncForm.digest = String(metadata.digest || '')
  draftSyncForm.cover_url =
    String(metadata.cover_url || '').trim() || extractFirstImageUrlFromText(String(draft.content || ''))
  draftSyncForm.queue_on_fail = true
  draftSyncForm.max_retries = 3
  draftDetailVisible.value = true
  if (!syncQuery) return
  setStudioQuery(
    {
      section: 'drafts',
      draft_id: draft.id,
    },
    'push'
  )
}

const toggleDraftEdit = () => {
  draftEditing.value = !draftEditing.value
  if (draftEditing.value) return
  draftEditForm.title = currentDraft.value?.title || ''
  draftEditForm.content = currentDraft.value?.content || ''
}

const copyCurrentDraft = async () => {
  const text = String(currentDraft.value?.content || '').trim()
  if (!text) {
    Message.warning('草稿内容为空')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    Message.success('草稿内容已复制')
  } catch (error) {
    Message.error('复制失败，请手动复制')
  }
}

const saveCurrentDraft = async () => {
  if (!currentDraft.value?.id) return
  const nextTitle = String(draftEditForm.title || '').trim()
  const nextContent = String(draftEditForm.content || '').trim()
  if (!nextContent) {
    Message.warning('草稿内容不能为空')
    return
  }
  draftSaving.value = true
  try {
    const updated = await updateDraft(currentDraft.value.id, {
      title: nextTitle,
      content: nextContent,
      platform: currentDraft.value.platform,
      mode: currentDraft.value.mode,
    })
    currentDraft.value = updated
    const idx = drafts.value.findIndex((item) => item.id === updated.id)
    if (idx >= 0) drafts.value[idx] = updated
    draftEditing.value = false
    Message.success('草稿已更新')
    await refreshOverview()
  } finally {
    draftSaving.value = false
  }
}

const removeCurrentDraft = async () => {
  if (!currentDraft.value?.id) return
  const targetId = currentDraft.value.id
  const targetTitle = currentDraft.value.title || '该草稿'
  Modal.confirm({
    title: '删除草稿',
    content: `确认删除「${targetTitle}」吗？删除后不可恢复。`,
    hideCancel: false,
    onOk: async () => {
      draftDeleting.value = true
      try {
        await deleteDraft(targetId)
        Message.success('草稿已删除')
        draftDetailVisible.value = false
        await fetchDrafts()
        await refreshOverview()
      } finally {
        draftDeleting.value = false
      }
    },
  })
}

const openDraftSync = () => {
  if (!currentDraft.value?.id) return
  draftSyncForm.title = currentDraft.value.title || ''
  draftSyncVisible.value = true
  openWhitelistReminder()
}

const submitDraftSync = async () => {
  if (!currentDraft.value?.id) {
    Message.error('草稿不存在')
    return false
  }
  const title = String(draftSyncForm.title || '').trim()
  if (!title) {
    Message.warning('请填写标题')
    return false
  }
  if (draftSyncForm.platform !== 'wechat') {
    Message.warning('当前仅支持同步到微信公众号草稿箱')
    return false
  }
  draftSyncing.value = true
  try {
    const resp = await syncDraftToWechat(currentDraft.value.id, {
      title,
      content: String(currentDraft.value.content || ''),
      author: draftSyncForm.author,
      digest: draftSyncForm.digest,
      cover_url: draftSyncForm.cover_url,
      platform: draftSyncForm.platform,
      queue_on_fail: draftSyncForm.queue_on_fail,
      max_retries: draftSyncForm.max_retries,
    })
    if (resp.wechat?.synced) {
      Message.success(resp.wechat.message || '已同步到公众号草稿箱')
    } else {
      Message.warning(resp.wechat?.message || '同步失败，已按策略进入重试')
    }
    await fetchPublishQueue()
    await refreshOverview()
    return true
  } catch (error: any) {
    Message.error(String(error || '同步失败'))
    return false
  } finally {
    draftSyncing.value = false
  }
}

const onPageChange = (page: number) => {
  pagination.current = page
  fetchArticles()
}

const applyPlan = (plan?: any) => {
  if (!plan) return
  overview.plan = plan
}

const buildResultCacheKey = (articleId: string, mode: string) => {
  return `${RESULT_CACHE_PREFIX}${articleId}:${mode}`
}

const cacheResultSnapshot = (title: string, sourceTitle: string, res: any) => {
  const articleId = String(res?.article_id || '').trim()
  const mode = String(res?.mode || '').trim()
  if (!articleId || !mode) return
  const snapshot: ResultSnapshot = {
    title: title || '创作结果',
    sourceTitle: sourceTitle || '',
    data: {
      article_id: articleId,
      mode: mode as any,
      result: String(res?.result || ''),
      recommended_tags: Array.isArray(res?.recommended_tags) ? res.recommended_tags : [],
      image_prompts: Array.isArray(res?.image_prompts) ? res.image_prompts : [],
      images: Array.isArray(res?.images) ? res.images : [],
      image_notice: String(res?.image_notice || ''),
      options: res?.options || {},
      plan: res?.plan,
    },
  }
  sessionStorage.setItem(buildResultCacheKey(articleId, mode), JSON.stringify(snapshot))
}

const applyResultSnapshot = (snapshot: ResultSnapshot, syncQuery: boolean) => {
  const data = snapshot?.data || ({} as AIComposeResult)
  resultTitle.value = snapshot?.title || '创作结果'
  resultSourceTitle.value = snapshot?.sourceTitle || ''
  resultData.article_id = data.article_id || ''
  resultData.mode = (data.mode || 'create') as any
  resultData.result = data.result || ''
  resultData.recommended_tags = data.recommended_tags || []
  resultData.image_prompts = data.image_prompts || []
  resultData.images = data.images || []
  resultData.image_notice = data.image_notice || ''
  applyPlan(data.plan)
  resultVisible.value = true
  if (syncQuery) {
    setStudioQuery({
      article_id: resultData.article_id || undefined,
      mode: resultData.mode || undefined,
    })
  }
}

const restoreResultSnapshotFromQuery = () => {
  const articleId = activeArticleId.value
  const mode = activeModeFromQuery.value
  if (!articleId || !mode) return false
  const raw = sessionStorage.getItem(buildResultCacheKey(articleId, mode))
  if (!raw) return false
  try {
    const snapshot = JSON.parse(raw) as ResultSnapshot
    applyResultSnapshot(snapshot, false)
    return true
  } catch (error) {
    return false
  }
}

const scrollToActiveDraft = (behavior: ScrollBehavior = 'smooth') => {
  if (!activeDraftId.value) return
  const el = document.getElementById(`draft-item-${activeDraftId.value}`)
  if (el) el.scrollIntoView({ behavior, block: 'center' })
}

const articleRowClass = ({ record }: any) => {
  if (!activeArticleId.value) return ''
  return String(record?.id || '') === activeArticleId.value ? 'active-article-row' : ''
}

const fillResult = (title: string, sourceTitle: string, res: any) => {
  resultTitle.value = title
  resultSourceTitle.value = sourceTitle || ''
  resultData.article_id = res.article_id || ''
  resultData.mode = res.mode || 'create'
  resultData.result = res.result || ''
  resultData.recommended_tags = res.recommended_tags || []
  resultData.image_prompts = res.image_prompts || []
  resultData.images = res.images || []
  resultData.image_notice = res.image_notice || ''
  applyPlan(res.plan)
  resultVisible.value = true
  setStudioQuery({
    article_id: resultData.article_id || undefined,
    mode: resultData.mode || undefined,
    draft_id: undefined,
  }, 'push')
  cacheResultSnapshot(title, sourceTitle, res)
  if (resultData.image_notice && resultData.image_notice.includes('自动回退')) {
    Message.warning(resultData.image_notice)
  }
}

const runTask = async (mode: 'analyze' | 'rewrite', record: any) => {
  const key = `${mode}:${record.id}`
  runningKey.value = key
  Message.info(`${mode === 'analyze' ? '正在分析' : '正在仿写'}，请稍候...`)
  try {
    const payload = {
      instruction: quickInstruction.value || '',
      platform: createForm.platform,
      style: createForm.style,
      length: createForm.length,
      image_count: 0,
      audience: createForm.audience,
      tone: createForm.tone,
      generate_images: false,
    }
    const res = mode === 'analyze' ? await aiAnalyze(record.id, payload) : await aiRewrite(record.id, payload)
    fillResult(mode === 'analyze' ? '分析结果' : '仿写结果', record.title || '', res)
  } catch (e: any) {
    handleActionableError(e)
  } finally {
    runningKey.value = ''
  }
}

const openCreate = (record: any) => {
  currentCreateArticle.value = record
  createForm.instruction = quickInstruction.value || ''
  createVisible.value = true
}

const submitCreate = async () => {
  if (!currentCreateArticle.value?.id) {
    Message.error('请选择要创作的文章')
    return
  }
  const record = currentCreateArticle.value
  const key = `create:${record.id}`
  runningKey.value = key
  createVisible.value = false
  Message.info('正在生成图文稿件，请稍候...')
  try {
    const payload = {
      instruction: createForm.instruction,
      platform: createForm.platform,
      style: createForm.style,
      length: createForm.length,
      image_count: createForm.image_count,
      audience: createForm.audience,
      tone: createForm.tone,
      generate_images: createForm.generate_images,
    }
    const res = await aiCreate(record.id, payload)
    fillResult('创作结果', record.title || '', res)
    await fetchDrafts()
  } catch (e: any) {
    handleActionableError(e)
  } finally {
    runningKey.value = ''
  }
}

const copyResult = async () => {
  if (!resultData.result) {
    Message.warning('没有可复制的内容')
    return
  }
  try {
    await navigator.clipboard.writeText(resultData.result)
    Message.success('已复制到剪贴板')
  } catch (e) {
    Message.error('复制失败，请手动复制')
  }
}

const extractFirstImageUrlFromText = (text: string) => {
  const source = String(text || '')
  const markdownMatch = source.match(/!\[[^\]]*\]\((https?:\/\/[^)\s]+)[^)]*\)/i)
  if (markdownMatch?.[1]) return String(markdownMatch[1]).trim()

  const htmlMatch = source.match(/<img[^>]+src=["'](https?:\/\/[^"']+)["']/i)
  if (htmlMatch?.[1]) return String(htmlMatch[1]).trim()
  return ''
}

const firstResultImageUrl = () => {
  const explicit = Array.isArray(resultData.images)
    ? resultData.images.find((url: any) => /^https?:\/\//i.test(String(url || '').trim()))
    : ''
  if (explicit) return String(explicit).trim()
  return extractFirstImageUrlFromText(String(resultData.result || ''))
}

const openPublish = () => {
  if (!resultData.article_id || !resultData.result) {
    Message.warning('请先生成内容')
    return
  }
  publishForm.title = resultSourceTitle.value || 'AI 创作草稿'
  publishForm.author = ''
  publishForm.digest = ''
  publishForm.cover_url = firstResultImageUrl()
  publishForm.sync_to_wechat = true
  publishForm.queue_on_fail = true
  publishForm.max_retries = 3
  publishVisible.value = true
  if (publishForm.sync_to_wechat) openWhitelistReminder()
}

const submitPublish = async () => {
  if (!resultData.article_id) {
    Message.error('缺少文章ID，无法发布')
    return false
  }
  if (!resultData.result?.trim()) {
    Message.error('没有发布内容')
    return false
  }
  publishLoading.value = true
  try {
    const effectiveCoverUrl = String(publishForm.cover_url || '').trim() || firstResultImageUrl()
    const resp = await publishDraft(resultData.article_id, {
      title: publishForm.title,
      content: resultData.result,
      digest: publishForm.digest,
      author: publishForm.author,
      cover_url: effectiveCoverUrl,
      mode: resultData.mode,
      platform: createForm.platform,
      sync_to_wechat: publishForm.sync_to_wechat,
      queue_on_fail: publishForm.queue_on_fail,
      max_retries: publishForm.max_retries,
    })
    applyPlan(resp.plan)
    await fetchDrafts()
    await fetchPublishQueue()
    await refreshOverview()
    if (resp.wechat?.synced) {
      Message.success(resp.wechat.message || '已发布到公众号草稿箱')
    } else {
      Message.warning(resp.wechat?.message || '已保存本地草稿箱')
    }
    return true
  } catch (e: any) {
    Message.error(String(e || '发布失败'))
    return false
  } finally {
    publishLoading.value = false
  }
}

const refreshAll = async () => {
  await Promise.all([refreshOverview(), fetchArticles(), fetchDrafts(), fetchPublishQueue()])
}

const restoreFromRouteQuery = () => {
  if (restoreResultSnapshotFromQuery()) {
    return
  }
  if (activeDraftId.value) {
    const target = drafts.value.find((item) => String(item?.id || '') === String(activeDraftId.value))
    if (target) {
      openDraftDetail(target, false)
      return
    }
    nextTick(() => scrollToActiveDraft('auto'))
    return
  }
  if (activeArticleId.value) {
    if (activeModeFromQuery.value === 'create') {
      const targetArticle = articles.value.find((item: any) => String(item?.id || '') === activeArticleId.value)
      if (targetArticle) {
        currentCreateArticle.value = targetArticle
        createForm.instruction = quickInstruction.value || ''
        createVisible.value = true
      }
    }
  }
}

watch(resultVisible, (visible) => {
  if (!visible) {
    setStudioQuery({
      article_id: undefined,
      mode: undefined,
    })
  }
})

watch(draftDetailVisible, (visible) => {
  if (!visible) {
    currentDraft.value = null
    draftEditing.value = false
    draftSyncVisible.value = false
    setStudioQuery({
      draft_id: undefined,
    })
  }
})

watch(
  () => publishForm.sync_to_wechat,
  (enabled) => {
    if (enabled && publishVisible.value) openWhitelistReminder()
  }
)

watch(
  () => globalWxAuthReady?.value,
  async (ready) => {
    if (ready && !overview.wechat_auth?.authorized) {
      await refreshOverview()
    }
  }
)

watch(
  () => route.fullPath,
  async () => {
    const nextMpId = getQueryText('mp_id')
    const nextSearch = getQueryText('search')
    const nextPage = parseQueryPage()
    const needRefetch =
      nextMpId !== activeMpId.value ||
      nextSearch !== searchText.value ||
      nextPage !== pagination.current
    if (needRefetch) {
      activeMpId.value = nextMpId
      searchText.value = nextSearch
      pagination.current = nextPage
      await fetchArticles(false)
    }
    restoreFromRouteQuery()
  }
)

onMounted(async () => {
  initFiltersFromQuery()
  await loadProfile()
  await loadComposeMeta()
  await fetchMps()
  await refreshAll()
  if (isDraftboxRoute.value && !getQueryText('section')) {
    setStudioQuery({ section: 'drafts' })
  }
  restoreFromRouteQuery()
})
</script>

<style scoped>
.studio-page {
  padding: 4px;
  font-family: 'Avenir Next', 'PingFang SC', 'Hiragino Sans GB', sans-serif;
  color: var(--text-2);
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 18px 20px;
  border-radius: 14px;
  margin-bottom: 14px;
  background: linear-gradient(130deg, #eef5ff 0%, #f8fbff 56%, #f0f9ff 100%);
  border: 1px solid #d9e5fb;
  color: var(--text-1);
}

.hero h1 {
  margin: 0;
  font-size: 24px;
  letter-spacing: 0.4px;
}

.hero p {
  margin: 6px 0 0;
  color: var(--text-3);
}

.studio-switcher {
  margin-bottom: 14px;
  padding: 10px 12px;
  border: 1px solid #d9e5fb;
  border-radius: 12px;
  background: #f8fbff;
}

.studio-layout {
  display: grid;
  grid-template-columns: 332px minmax(0, 1fr);
  gap: 14px;
}

.studio-layout.draftbox-mode {
  grid-template-columns: minmax(0, 1fr);
}

.studio-tools {
  display: grid;
  gap: 12px;
  height: fit-content;
  position: sticky;
  top: 10px;
}

.studio-display {
  min-width: 0;
}

.studio-display.full {
  width: 100%;
}

.summary-row {
  margin-bottom: 14px;
}

.summary-card {
  min-height: 206px;
}

.plan-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.quota-line {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.metric {
  background: #f8fbff;
  border: 1px solid #dde7f8;
  border-radius: 10px;
  padding: 12px;
  text-align: center;
}

.metric .value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-1);
}

.metric .label {
  font-size: 12px;
  color: var(--text-3);
}

.panel {
  margin-bottom: 14px;
}

.activity-metrics {
  margin-bottom: 12px;
}

.activity-metric {
  background: #f8fbff;
  border: 1px solid #dde7f8;
  border-radius: 10px;
  padding: 10px 12px;
}

.activity-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-1);
}

.activity-label {
  color: var(--text-3);
  font-size: 12px;
}

.activity-trend {
  display: grid;
  gap: 10px;
}

.activity-item {
  border: 1px solid #dde6f7;
  border-radius: 10px;
  padding: 8px 10px;
  background: #fcfdff;
}

.activity-date {
  font-size: 12px;
  color: #1d4ed8;
  margin-bottom: 4px;
}

.activity-bar-row {
  display: grid;
  grid-template-columns: 22px 1fr 30px;
  gap: 8px;
  align-items: center;
}

.bar-name {
  font-size: 12px;
  color: var(--text-3);
}

.bar-track {
  height: 8px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 999px;
}

.bar-fill.draft {
  background: linear-gradient(90deg, #2563eb 0%, #60a5fa 100%);
}

.bar-fill.success {
  background: linear-gradient(90deg, #16a34a 0%, #4ade80 100%);
}

.bar-value {
  text-align: right;
  font-size: 12px;
  color: var(--text-2);
}

.muted {
  color: var(--text-3);
  font-size: 12px;
}

.section-chip-row {
  display: flex;
  align-items: flex-start;
  align-content: flex-start;
  gap: 8px;
  flex-wrap: wrap;
}

.workbench-toolbar {
  position: sticky;
  top: 8px;
  z-index: 8;
  padding: 8px;
  border-radius: 10px;
  border: 1px solid #dce6f8;
  background: #f8fbff;
  backdrop-filter: blur(6px);
}

.quick-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.platform-grid {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.platform-item {
  border: 1px solid #dce6f8;
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  background: #ffffff;
  min-height: 108px;
}

.platform-item.active {
  border-color: rgb(var(--primary-6));
  box-shadow: 0 0 0 2px rgba(var(--primary-3), 0.25);
}

.platform-item input {
  display: none;
}

.platform-item img {
  width: 36px;
  height: 36px;
}

.platform-name {
  font-weight: 600;
}

.platform-desc {
  color: var(--text-3);
  font-size: 12px;
  line-height: 1.4;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.image-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gen-image {
  width: 100%;
  border-radius: 8px;
  border: 1px solid #dce6f8;
}

.draft-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.whitelist-ip-list {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

:deep(.platform-form-item .arco-form-item-content-wrapper) {
  width: 100%;
}

:deep(.arco-card) {
  background: #ffffff;
  border: 1px solid #dce6f8;
}

:deep(.arco-card-header-title),
:deep(.arco-typography),
:deep(.arco-table-th),
:deep(.arco-table-td) {
  color: var(--text-2);
}

:deep(.active-draft-item) {
  background: #edf4ff;
  border-left: 2px solid #2563eb;
}

:deep(.active-article-row > td) {
  background: #edf4ff !important;
}

@media (max-width: 1200px) {
  .studio-layout {
    grid-template-columns: 1fr;
  }

  .studio-tools {
    position: static;
  }

  .platform-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .studio-page {
    padding: 0;
  }

  .hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .platform-grid {
    grid-template-columns: 1fr;
  }
}
</style>
