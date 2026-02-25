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
        <a-button v-if="!isAllFreeMode" type="outline" @click="goBilling">套餐订阅</a-button>
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

    <div class="studio-layout">
      <section class="studio-display">
        <a-row :gutter="16" class="summary-row">
          <a-col :xs="24" :md="8">
            <a-card class="summary-card" :loading="overviewLoading">
              <template #title>创作额度</template>
              <a-space direction="vertical" fill>
                <div class="quota-line">
                  <span>AI 日额度</span>
                  <span>{{ overview.stats?.daily_ai_used || 0 }}/{{ overview.stats?.daily_ai_limit || 60 }}</span>
                </div>
                <a-progress :percent="quotaPercent(overview.stats?.daily_ai_used, overview.stats?.daily_ai_limit)" />
                <div class="muted">
                  今日剩余 {{ overview.stats?.daily_ai_remaining ?? 0 }} 次
                </div>
                <div class="quota-line">
                  <span>图片配额</span>
                  <span>{{ overview.plan?.image_used || 0 }}/{{ overview.plan?.image_quota || 0 }}</span>
                </div>
                <a-progress :percent="quotaPercent(overview.plan?.image_used, overview.plan?.image_quota)" status="success" />
                <a-button v-if="!isAllFreeMode" size="small" type="outline" @click="goBilling">升级套餐能力</a-button>
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
                  <span>{{ overview.plan?.can_publish_wechat_draft ? '已开通' : isAllFreeMode ? '免费开放中' : '套餐未开通' }}</span>
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
                <a-button type="text" :loading="isActionRunning(`analyze:${record.id}`)" @click="handleModeAction('analyze', record)">
                  {{ modeActionLabel('analyze', record) }}
                </a-button>
                <a-button type="text" :loading="isActionRunning(`create:${record.id}`)" @click="handleModeAction('create', record)">
                  {{ modeActionLabel('create', record) }}
                </a-button>
                <a-button type="text" :loading="isActionRunning(`rewrite:${record.id}`)" @click="handleModeAction('rewrite', record)">
                  {{ modeActionLabel('rewrite', record) }}
                </a-button>
              </a-space>
            </template>
          </a-table>
        </a-card>

        <a-card v-if="activeSection === 'drafts'" id="studio-drafts-card" title="草稿历史（本地草稿箱）" class="panel" :loading="draftLoading">
          <a-space style="margin-bottom: 10px;" wrap>
            <a-checkbox
              :model-value="allDraftSelected"
              :indeterminate="selectedDraftCount > 0 && !allDraftSelected"
              @change="(v) => toggleSelectAllDrafts(!!v)"
            >
              全选
            </a-checkbox>
            <span class="muted">已选 {{ selectedDraftCount }} 条</span>
            <a-button
              size="small"
              status="danger"
              :disabled="selectedDraftCount === 0"
              :loading="draftDeleting"
              @click="removeSelectedDrafts"
            >
              批量删除
            </a-button>
          </a-space>
          <a-list :data="drafts">
            <template #item="{ item }">
              <a-list-item :id="`draft-item-${item.id}`" :class="{ 'active-draft-item': item.id === activeDraftId }">
                <div style="width: 100%;">
                  <div class="draft-head">
                    <a-space>
                      <a-checkbox
                        :model-value="isDraftSelected(item.id)"
                        @change="(v) => toggleDraftSelection(item.id, !!v)"
                        @click.stop
                      />
                      <a-link @click="openDraftDetail(item)">{{ item.title }}</a-link>
                    </a-space>
                    <a-space>
                      <a-tag :color="draftModeColor(item.mode)">{{ draftModeLabel(item.mode) }}</a-tag>
                      <a-tag
                        v-if="draftWechatStatusLabel(item)"
                        :color="draftWechatStatusColor(item)"
                      >
                        {{ draftWechatStatusLabel(item) }}
                      </a-tag>
                      <span class="muted">{{ item.created_at }}</span>
                    </a-space>
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
          <a-button :loading="isActionRunning(`${resultData.mode}:${resultData.article_id}`)" @click="regenerateCurrentResult">
            {{ resultRegenerateLabel }}
          </a-button>
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

        <div class="result-editor-wrap">
          <div class="muted">Markdown 文稿（可编辑）。选中一段内容后可直接生成内容配图并插入文稿。</div>
          <textarea
            ref="resultEditorRef"
            v-model="resultData.result"
            class="result-editor"
            placeholder="请先执行分析/创作/仿写生成结果"
            @mouseup="captureResultSelection"
            @keyup="captureResultSelection"
            @select="captureResultSelection"
          />
        </div>

        <div v-if="selectedResultText" class="inline-illustration-bar">
          <span>已选中 {{ selectedResultText.length }} 字：{{ selectedResultTextPreview }}</span>
          <a-button size="mini" type="primary" :loading="inlineImageLoading" @click="generateInlineImageFromSelection">
            生成内容配图
          </a-button>
        </div>
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
        <a-alert type="info" style="margin-bottom: 12px;">
          公众号同步将自动读取个人中心中的 AppID/AppSecret（个人中心 -> 修改个人信息）。
        </a-alert>
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
          <a-space>
            <strong>{{ currentDraft?.title || '-' }}</strong>
            <a-tag
              v-if="currentDraft && draftWechatStatusLabel(currentDraft)"
              :color="draftWechatStatusColor(currentDraft)"
            >
              {{ draftWechatStatusLabel(currentDraft) }}
            </a-tag>
          </a-space>
          <span class="muted">{{ currentDraft?.created_at || '' }}</span>
        </div>
        <div class="muted">
          文章ID：{{ currentDraft?.article_id || '-' }} | 平台：{{ currentDraft?.platform || '-' }} | 类型：{{ draftModeLabel(currentDraft?.mode || '') }}
        </div>
        <a-space wrap>
          <a-button size="small" @click="copyCurrentDraft">复制草稿</a-button>
          <a-button size="small" @click="toggleDraftEdit">{{ draftEditing ? '取消编辑' : '编辑草稿' }}</a-button>
          <a-button v-if="draftEditing" size="small" type="primary" :loading="draftSaving" @click="saveCurrentDraft">保存修改</a-button>
          <a-button size="small" type="primary" :loading="draftRegenerating" @click="regenerateCurrentDraft">重新生成</a-button>
          <a-button size="small" type="outline" :loading="draftSyncing" @click="openDraftSync">同步到公众号</a-button>
          <a-button size="small" status="danger" :loading="draftDeleting" @click="removeCurrentDraft">删除</a-button>
        </a-space>
        <a-divider style="margin: 8px 0;" />
        <div v-if="currentDraftDeliveryHistory.length" class="draft-delivery-log">
          <div class="muted draft-delivery-title">同步日志</div>
          <div v-for="(item, idx) in currentDraftDeliveryHistory" :key="`delivery-${idx}`" class="draft-delivery-item">
            <a-space wrap size="small">
              <a-tag :color="deliveryStatusColor(item.status)">{{ deliveryStatusLabel(item.status) }}</a-tag>
              <span class="muted">{{ item.time || '-' }}</span>
              <span v-if="item.source" class="muted">来源：{{ item.source }}</span>
            </a-space>
            <div class="draft-delivery-message">{{ item.message || '（无详细信息）' }}</div>
            <pre v-if="deliveryExtraPreview(item)" class="draft-delivery-extra">{{ deliveryExtraPreview(item) }}</pre>
          </div>
        </div>
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
        <template v-else>
          <div class="muted" style="margin-bottom: 4px; font-size: 12px;">Markdown 文稿。选中一段文字后可生成内容配图并插入草稿。</div>
          <div
            class="draft-rendered"
            v-html="renderDraftMarkdown(currentDraft?.content || '')"
            @mouseup="captureDraftSelection"
          />
          <div v-if="selectedDraftText" class="inline-illustration-bar">
            <span>已选中 {{ selectedDraftText.length }} 字：{{ selectedDraftTextPreview }}</span>
            <a-button size="mini" type="primary" :loading="draftInlineImageLoading" @click="generateInlineImageFromDraftSelection">
              生成内容配图
            </a-button>
          </div>
        </template>
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
        <a-alert type="info" style="margin-bottom: 12px;">
          将自动读取个人中心中的 AppID/AppSecret；若未配置，后端会返回引导提示。
        </a-alert>
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
import { computed, inject, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { marked } from 'marked'
import { Message, Modal } from '@arco-design/web-vue'
import { useRoute, useRouter } from 'vue-router'
import {
  aiAnalyze,
  aiCreate,
  aiRewrite,
  getComposeOptions,
  recommendTags,
  getWorkbenchOverview,
  getDrafts,
  updateDraft,
  deleteDraft,
  deleteDraftBatch,
  syncDraftToWechat,
  publishDraft,
  generateInlineIllustration,
  getComposeTask,
  getComposeTasks,
  getPublishTasks,
  processPublishTasks,
  retryPublishTask,
  deletePublishTask,
  type AIComposeResult,
  type ComposeTask,
  type DraftRecord,
  type PublishTask,
} from '@/api/ai'
import { getArticles } from '@/api/article'
import { getSubscriptions } from '@/api/subscription'
import { loadRuntimeSettings } from '@/utils/runtime'

import logoWechat from '@/assets/platform/wechat.svg'
import logoXhs from '@/assets/platform/xiaohongshu.svg'
import logoZhihu from '@/assets/platform/zhihu.svg'
import logoTwitter from '@/assets/platform/twitter.svg'

type StudioSection = 'workbench' | 'drafts' | 'queue'
type ComposeMode = 'analyze' | 'create' | 'rewrite'
type SectionTab = {
  key: StudioSection
  label: string
}
type ComposeTaskContext = {
  mode: ComposeMode
  articleId: string
  sourceTitle: string
}
const WECHAT_WHITELIST_REMINDER_NEVER_KEY = 'studio:wechat-whitelist-reminder:never'
const DRAFT_LOOKUP_LIMIT = 200  // 匹配后端 API 最大限制 (le=200)
const COMPOSE_TASK_POLL_INTERVAL_MS = 1500
const COMPOSE_TASK_POLL_MAX_RETRIES = 240

const showAuthQrcode = inject<() => void>('showAuthQrcode')
const globalWxAuthReady = inject<{ value: boolean } | null>('wxAuthReady', null)
const route = useRoute()
const router = useRouter()

const overviewLoading = ref(false)
const draftLoading = ref(false)
const queueLoading = ref(false)
const processingQueue = ref(false)
const loading = ref(false)
const runningActions = reactive<Record<string, boolean>>({})
const composeTaskTimers = new Map<string, number>()
const composeTaskAttempts = reactive<Record<string, number>>({})
const composeTaskPollingLocks = new Set<string>()
const runtimeSettings = ref({
  product_mode: 'all_free',
  is_all_free: true,
  billing_visible: false,
  analytics_enabled: true,
})

const overview = reactive<any>({
  plan: null,
  stats: {},
  activity: { trend: [] },
  wechat_auth: {},
  wechat_whitelist: {},
  recent_drafts: [],
})

const drafts = ref<DraftRecord[]>([])
const selectedDraftIds = ref<string[]>([])
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
const draftRegenerating = ref(false)
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
  image_count: 2,
  audience: '',
  tone: '',
  instruction: '',
  generate_images: true,
})

const resultVisible = ref(false)
const resultTitle = ref('创作结果')
const resultEditorRef = ref<HTMLTextAreaElement | null>(null)
const selectedResultText = ref('')
const inlineImageLoading = ref(false)
const selectedDraftText = ref('')
const draftInlineImageLoading = ref(false)
const resultData = reactive<AIComposeResult>({
  article_id: '',
  mode: 'create',
  result: '',
  source_title: '',
  recommended_tags: [],
  image_prompts: [],
  images: [],
  image_notice: '',
  options: {},
  from_cache: false,
  cached_at: '',
  result_id: '',
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

const isAllFreeMode = computed(() => !!runtimeSettings.value?.is_all_free)
const activeArticleId = computed(() => getQueryText('article_id'))
const activeModeFromQuery = computed(() => getQueryText('mode'))
const activeDraftId = computed(() => getQueryText('draft_id'))
const pageTitle = computed(() => '创作中台')
const pageDesc = computed(() => '将创作工作台、草稿管理和投递队列拆分为子页面，提高操作聚焦度。')
const activeSection = computed<StudioSection>(() => {
  const section = getQueryText('section').trim().toLowerCase()
  if (section === 'queue') return 'queue'
  if (section === 'drafts' || activeDraftId.value) return 'drafts'
  return 'workbench'
})
const sectionTabs = computed<SectionTab[]>(() => {
  return [
    { key: 'workbench', label: '创作工作台' },
    { key: 'drafts', label: '本地草稿' },
    { key: 'queue', label: '投递队列' },
  ]
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
const resultRegenerateLabel = computed(() => {
  if (resultData.mode === 'analyze') return '重新分析'
  if (resultData.mode === 'rewrite') return '重新仿写'
  return '重新创作'
})
const selectedResultTextPreview = computed(() => {
  const text = String(selectedResultText.value || '').trim()
  if (!text) return ''
  return text.length > 42 ? `${text.slice(0, 42)}...` : text
})
const selectedDraftTextPreview = computed(() => {
  const text = String(selectedDraftText.value || '').trim()
  if (!text) return ''
  return text.length > 42 ? `${text.slice(0, 42)}...` : text
})
const selectedDraftCount = computed(() => selectedDraftIds.value.length)
const allDraftSelected = computed(() => {
  if (!drafts.value.length) return false
  const selected = new Set(selectedDraftIds.value.map((id) => String(id || '').trim()).filter(Boolean))
  if (!selected.size) return false
  return drafts.value.every((item) => selected.has(String(item.id || '').trim()))
})
const renderDraftMarkdown = (content: string): string => {
  if (!content) return '<p style="color:var(--color-text-3)">暂无内容</p>'
  return marked.parse(content) as string
}
const draftDeliveryInfo = (draft: DraftRecord) => {
  const metadata = (draft?.metadata || {}) as Record<string, any>
  const delivery = (metadata.delivery || {}) as Record<string, any>
  const wechat = (delivery.wechat || {}) as Record<string, any>
  const status = String(wechat.status || '').trim().toLowerCase()
  return {
    status,
    deliveredAt: String(wechat.delivered_at || wechat.last_try_at || ''),
    message: String(wechat.message || ''),
  }
}
type DraftDeliveryHistoryItem = {
  status: string
  message: string
  time: string
  source?: string
  task_id?: string
  extra?: Record<string, any>
}
const currentDraftDeliveryHistory = computed<DraftDeliveryHistoryItem[]>(() => {
  const metadata = ((currentDraft.value?.metadata || {}) as Record<string, any>)
  const delivery = (metadata.delivery || {}) as Record<string, any>
  const wechat = (delivery.wechat || {}) as Record<string, any>
  const history = Array.isArray(wechat.history) ? wechat.history : []
  const rows = history
    .map((item: any) => {
      const row = (item || {}) as Record<string, any>
      return {
        status: String(row.status || '').trim().toLowerCase(),
        message: String(row.message || ''),
        time: String(row.time || ''),
        source: String(row.source || ''),
        task_id: String(row.task_id || ''),
        extra: (row.extra && typeof row.extra === 'object') ? (row.extra as Record<string, any>) : undefined,
      }
    })
    .filter((item: DraftDeliveryHistoryItem) => !!item.status || !!item.message || !!item.time)
  if (rows.length) return rows
  const fallbackDraft = currentDraft.value
  if (!fallbackDraft) return []
  const fallback = draftDeliveryInfo(fallbackDraft)
  if (!fallback.status && !fallback.message && !fallback.deliveredAt) return []
  return [
    {
      status: fallback.status,
      message: fallback.message,
      time: fallback.deliveredAt,
      source: 'draft_delivery',
    },
  ]
})
const deliveryStatusLabel = (status: string) => {
  const key = String(status || '').trim().toLowerCase()
  if (key === 'success') return '成功'
  if (key === 'failed') return '失败'
  if (key === 'pending' || key === 'processing') return '处理中'
  return '未知'
}
const deliveryStatusColor = (status: string) => {
  const key = String(status || '').trim().toLowerCase()
  if (key === 'success') return 'green'
  if (key === 'failed') return 'red'
  if (key === 'pending' || key === 'processing') return 'arcoblue'
  return 'gray'
}
const deliveryExtraPreview = (item: DraftDeliveryHistoryItem) => {
  const extra = item?.extra
  if (!extra || typeof extra !== 'object') return ''
  try {
    const json = JSON.stringify(extra, null, 2)
    return json.length > 800 ? `${json.slice(0, 800)}...` : json
  } catch (_) {
    return String(extra || '')
  }
}
const draftModeLabel = (mode: string) => {
  if (mode === 'analyze') return '分析'
  if (mode === 'rewrite') return '仿写'
  return '创作'
}
const draftModeColor = (mode: string) => {
  if (mode === 'analyze') return 'orange'
  if (mode === 'rewrite') return 'purple'
  return 'arcoblue'
}
const draftWechatStatusLabel = (draft: DraftRecord) => {
  const status = draftDeliveryInfo(draft).status
  if (status === 'success') return '已投递微信公众号'
  if (status === 'failed') return '公众号投递失败'
  if (status === 'pending' || status === 'processing') return '公众号投递中'
  return ''
}
const draftWechatStatusColor = (draft: DraftRecord) => {
  const status = draftDeliveryInfo(draft).status
  if (status === 'success') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'pending' || status === 'processing') return 'arcoblue'
  return 'gray'
}
const isDraftSelected = (draftId: string) => selectedDraftIds.value.includes(String(draftId || '').trim())
const toggleDraftSelection = (draftId: string, checked: boolean) => {
  const id = String(draftId || '').trim()
  if (!id) return
  const set = new Set(selectedDraftIds.value.map((item) => String(item || '').trim()).filter(Boolean))
  if (checked) set.add(id)
  else set.delete(id)
  selectedDraftIds.value = Array.from(set)
}
const toggleSelectAllDrafts = (checked: boolean) => {
  if (!checked) {
    selectedDraftIds.value = []
    return
  }
  selectedDraftIds.value = drafts.value.map((item) => String(item.id || '').trim()).filter(Boolean)
}
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

const latestDraftByArticleMode = computed<Record<string, DraftRecord>>(() => {
  const mapping: Record<string, DraftRecord> = {}
  ;(drafts.value || []).forEach((item) => {
    const articleId = String(item?.article_id || '').trim()
    const mode = String(item?.mode || '').trim().toLowerCase()
    if (!articleId || !mode) return
    const key = `${articleId}:${mode}`
    if (!mapping[key]) mapping[key] = item
  })
  return mapping
})

const getDraftForMode = (record: any, mode: ComposeMode): DraftRecord | null => {
  const articleId = String(record?.id || '').trim()
  if (!articleId) return null
  return latestDraftByArticleMode.value[`${articleId}:${mode}`] || null
}

const modeActionLabel = (mode: ComposeMode, record: any) => {
  return getDraftForMode(record, mode) ? '查看' : (mode === 'analyze' ? '分析' : mode === 'create' ? '创作' : '仿写')
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
  if (isAllFreeMode.value) {
    Message.info('当前处于全站免费模式，套餐与支付面板暂未开放')
    return
  }
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

const handleActionableError = (error: any) => {
  // Extract error message from various error formats
  const msg = error instanceof Error
    ? error.message
    : String(error?.message || error?.response?.data?.message || error || '操作失败')
  if (msg.includes('API Key') || msg.includes('AI 配置')) {
    Message.error('平台 AI 服务暂不可用，请稍后重试或联系管理员')
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

const composeModeLabel = (mode: ComposeMode) => {
  if (mode === 'analyze') return '分析'
  if (mode === 'rewrite') return '仿写'
  return '创作'
}

const composeActionKey = (mode: ComposeMode, articleId: string) => `${mode}:${articleId}`
const isActionRunning = (key: string) => !!runningActions[key]
const setActionRunning = (key: string, running: boolean) => {
  if (!key) return
  if (running) {
    runningActions[key] = true
    return
  }
  delete runningActions[key]
}

const clearComposeTaskWatcher = (taskId: string) => {
  const timer = composeTaskTimers.get(taskId)
  if (typeof timer === 'number') {
    window.clearInterval(timer)
    composeTaskTimers.delete(taskId)
  }
  composeTaskPollingLocks.delete(taskId)
  delete composeTaskAttempts[taskId]
}

const shouldAutoOpenComposeResult = (ctx: ComposeTaskContext) => {
  if (!resultVisible.value) return true
  return (
    String(resultData.article_id || '').trim() === ctx.articleId &&
    String(resultData.mode || '').trim().toLowerCase() === ctx.mode
  )
}

const handleComposeTaskResolved = async (task: ComposeTask, ctx: ComposeTaskContext) => {
  const status = String(task?.status || '').trim().toLowerCase()
  if (status === 'success') {
    const payload = task?.result_payload as AIComposeResult | undefined
    if (payload?.result && shouldAutoOpenComposeResult(ctx)) {
      fillResult(`${composeModeLabel(ctx.mode)}结果`, ctx.sourceTitle || payload.source_title || '', payload)
      Message.success(`${composeModeLabel(ctx.mode)}任务已完成`)
    } else {
      Message.success(`${composeModeLabel(ctx.mode)}任务已完成，结果已保存到草稿箱`)
    }
    await Promise.all([refreshOverview(), fetchDrafts()])
    return
  }
  const message = String(task?.error_message || task?.status_message || `${composeModeLabel(ctx.mode)}任务执行失败`)
  Message.error(message)
}

const startComposeTaskPolling = (taskId: string, ctx: ComposeTaskContext) => {
  const id = String(taskId || '').trim()
  if (!id || composeTaskTimers.has(id)) return
  composeTaskAttempts[id] = 0
  const timer = window.setInterval(async () => {
    if (composeTaskPollingLocks.has(id)) return
    composeTaskPollingLocks.add(id)
    try {
      composeTaskAttempts[id] = Number(composeTaskAttempts[id] || 0) + 1
      const task = await getComposeTask(id)
      const status = String(task?.status || '').trim().toLowerCase()
      if (status === 'pending' || status === 'processing') {
        if (composeTaskAttempts[id] >= COMPOSE_TASK_POLL_MAX_RETRIES) {
          clearComposeTaskWatcher(id)
          Message.warning(`${composeModeLabel(ctx.mode)}任务仍在后台处理中，请稍后在草稿箱查看结果`)
        }
        return
      }
      clearComposeTaskWatcher(id)
      await handleComposeTaskResolved(task, ctx)
    } catch (error: any) {
      if (composeTaskAttempts[id] >= COMPOSE_TASK_POLL_MAX_RETRIES) {
        clearComposeTaskWatcher(id)
        Message.warning(`${composeModeLabel(ctx.mode)}任务状态查询超时，请稍后在草稿箱刷新`)
      }
      if (String(error || '').includes('任务不存在')) {
        clearComposeTaskWatcher(id)
      }
    } finally {
      composeTaskPollingLocks.delete(id)
    }
  }, COMPOSE_TASK_POLL_INTERVAL_MS)
  composeTaskTimers.set(id, timer)
}

const submitComposeTask = async (mode: ComposeMode, record: any, payload: Record<string, any>) => {
  const articleId = String(record?.id || '').trim()
  if (!articleId) {
    Message.error('缺少文章ID，无法提交任务')
    return
  }
  const actionKey = composeActionKey(mode, articleId)
  setActionRunning(actionKey, true)
  try {
    const submit = mode === 'analyze'
      ? await aiAnalyze(articleId, payload)
      : (mode === 'create' ? await aiCreate(articleId, payload) : await aiRewrite(articleId, payload))
    const task = submit?.task
    if (!task?.id) {
      setActionRunning(actionKey, false)
      Message.error('任务提交失败，请稍后重试')
      return
    }
    setActionRunning(actionKey, false)
    const ahead = Math.max(0, Number(submit.queued_total || 0) - 1)
    if (ahead > 0) {
      Message.info(`${composeModeLabel(mode)}任务已入队，前方还有 ${ahead} 个任务`)
    } else {
      Message.info(`${composeModeLabel(mode)}任务已提交，正在处理中`)
    }
    startComposeTaskPolling(task.id, {
      mode,
      articleId,
      sourceTitle: String(record?.title || resultSourceTitle.value || resultData.source_title || ''),
    })
  } catch (error: any) {
    setActionRunning(actionKey, false)
    await handleComposeRequestError(error, articleId, mode)
  }
}

const recoverPendingComposeTasks = async () => {
  const pendingTasks = await getComposeTasks({ status: 'pending,processing', limit: 50 })
  for (const task of pendingTasks || []) {
    const mode = String(task?.mode || '').trim().toLowerCase() as ComposeMode
    const articleId = String(task?.article_id || '').trim()
    if (!articleId || (mode !== 'analyze' && mode !== 'create' && mode !== 'rewrite')) continue
    startComposeTaskPolling(String(task.id || ''), {
      mode,
      articleId,
      sourceTitle: getArticleRecordById(articleId).title || '',
    })
  }
}

const handleComposeRequestError = async (error: any, _articleId: string, _mode: ComposeMode) => {
  handleActionableError(error)
}

const openArticle = (id: string) => {
  window.open(`/views/article/${id}?auto_fetch=1`, '_blank')
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
    drafts.value = await getDrafts(DRAFT_LOOKUP_LIMIT)
    const available = new Set((drafts.value || []).map((item) => String(item.id || '').trim()).filter(Boolean))
    selectedDraftIds.value = selectedDraftIds.value.filter((id) => available.has(String(id || '').trim()))
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

const removeSelectedDrafts = async () => {
  const ids = Array.from(new Set(selectedDraftIds.value.map((item) => String(item || '').trim()).filter(Boolean)))
  if (!ids.length) {
    Message.warning('请先选择草稿')
    return
  }
  Modal.confirm({
    title: '批量删除草稿',
    content: `确认删除已选 ${ids.length} 条草稿吗？删除后不可恢复。`,
    hideCancel: false,
    onOk: async () => {
      draftDeleting.value = true
      try {
        const resp = await deleteDraftBatch(ids)
        if (currentDraft.value?.id && ids.includes(String(currentDraft.value.id || '').trim())) {
          draftDetailVisible.value = false
        }
        selectedDraftIds.value = []
        await fetchDrafts()
        await refreshOverview()
        Message.success(`已删除 ${resp.deleted || 0} 条草稿`)
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

const regenerateCurrentDraft = async () => {
  if (!currentDraft.value) {
    Message.warning('草稿不存在')
    return
  }

  const articleId = String(currentDraft.value.article_id || '').trim()
  const mode = String(currentDraft.value.mode || '').trim().toLowerCase() as ComposeMode

  if (!articleId || !mode) {
    Message.warning('缺少文章ID或模式信息，无法重新生成')
    return
  }

  // 关闭草稿详情弹窗
  draftDetailVisible.value = false

  // 获取文章记录
  const articleRecord = getArticleRecordById(articleId)

  // 根据模式执行重新生成
  if (mode === 'analyze' || mode === 'rewrite') {
    await runTask(mode as 'analyze' | 'rewrite', articleRecord, true)
  } else if (mode === 'create') {
    const metadata = (currentDraft.value.metadata || {}) as Record<string, any>
    const options = metadata.options || {}
    const payload = {
      instruction: String(options.instruction || metadata.instruction || ''),
      platform: String(options.platform || 'wechat'),
      style: String(options.style || '专业深度'),
      length: String(options.length || 'medium'),
      image_count: Number(options.image_count ?? 2),
      audience: String(options.audience || ''),
      tone: String(options.tone || ''),
      generate_images: Boolean(options.generate_images ?? true),
      force_refresh: true,
    }
    await submitComposeTask('create', articleRecord, payload)
  }
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
    if (resp.draft?.id) {
      currentDraft.value = resp.draft
    }
    await fetchDrafts()
    if (currentDraft.value?.id) {
      const latest = drafts.value.find((item) => item.id === currentDraft.value?.id)
      if (latest) currentDraft.value = latest
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
  resultSourceTitle.value = sourceTitle || res.source_title || ''
  resultData.article_id = res.article_id || ''
  resultData.mode = res.mode || 'create'
  resultData.result = res.result || ''
  resultData.source_title = res.source_title || sourceTitle || ''
  resultData.recommended_tags = res.recommended_tags || []
  resultData.image_prompts = res.image_prompts || []
  resultData.images = res.images || []
  resultData.image_notice = res.image_notice || ''
  resultData.options = res.options || {}
  resultData.from_cache = !!res.from_cache
  resultData.cached_at = res.cached_at || ''
  resultData.result_id = res.result_id || ''
  applyPlan(res.plan)
  resultVisible.value = true
  setStudioQuery({
    article_id: resultData.article_id || undefined,
    mode: resultData.mode || undefined,
    draft_id: undefined,
  }, 'push')
  if (resultData.image_notice && resultData.image_notice.includes('自动回退')) {
    Message.warning(resultData.image_notice)
  }
}

const runTask = async (mode: 'analyze' | 'rewrite', record: any, forceRefresh: boolean = false) => {
  const payload = {
    instruction: quickInstruction.value || '',
    platform: createForm.platform,
    style: createForm.style,
    length: createForm.length,
    image_count: 0,
    audience: createForm.audience,
    tone: createForm.tone,
    generate_images: false,
    force_refresh: forceRefresh,
  }
  await submitComposeTask(mode, record, payload)
}

const openCreate = (record: any) => {
  currentCreateArticle.value = record
  createForm.instruction = quickInstruction.value || ''
  createVisible.value = true
}

const handleModeAction = async (mode: ComposeMode, record: any) => {
  const existing = getDraftForMode(record, mode)
  if (existing) {
    openDraftDetail(existing)
    return
  }
  if (mode === 'create') {
    openCreate(record)
    return
  }
  await runTask(mode, record)
}

const submitCreate = async () => {
  if (!currentCreateArticle.value?.id) {
    Message.error('请选择要创作的文章')
    return
  }
  const record = currentCreateArticle.value
  createVisible.value = false
  const payload = {
    instruction: createForm.instruction,
    platform: createForm.platform,
    style: createForm.style,
    length: createForm.length,
    image_count: createForm.image_count,
    audience: createForm.audience,
    tone: createForm.tone,
    generate_images: createForm.generate_images,
    force_refresh: false,
  }
  await submitComposeTask('create', record, payload)
}

const getArticleRecordById = (articleId: string) => {
  const target = articles.value.find((item: any) => String(item?.id || '') === String(articleId || ''))
  if (target) return target
  return {
    id: articleId,
    title: resultSourceTitle.value || resultData.source_title || '未命名文章',
  }
}

const createPayloadFromResultOptions = (forceRefresh: boolean) => {
  const opts = (resultData.options || {}) as Record<string, any>
  return {
    instruction: createForm.instruction || quickInstruction.value || '',
    platform: String(opts.platform || createForm.platform || 'wechat'),
    style: String(opts.style || createForm.style || '专业深度'),
    length: String(opts.length || createForm.length || 'medium'),
    image_count: Number(opts.image_count ?? createForm.image_count ?? 2),
    audience: String(opts.audience || createForm.audience || ''),
    tone: String(opts.tone || createForm.tone || ''),
    generate_images: Boolean(opts.generate_images ?? createForm.generate_images),
    force_refresh: forceRefresh,
  }
}

const regenerateCurrentResult = async () => {
  const articleId = String(resultData.article_id || '').trim()
  const mode = String(resultData.mode || '').trim()
  if (!articleId || !mode) {
    Message.warning('缺少结果上下文，无法重新生成')
    return
  }

  if (mode === 'analyze' || mode === 'rewrite') {
    await runTask(mode as 'analyze' | 'rewrite', getArticleRecordById(articleId), true)
    return
  }
  const payload = createPayloadFromResultOptions(true)
  await submitComposeTask('create', getArticleRecordById(articleId), payload)
}

const captureResultSelection = () => {
  const el = resultEditorRef.value
  if (!el) {
    selectedResultText.value = ''
    return
  }
  const start = Number(el.selectionStart || 0)
  const end = Number(el.selectionEnd || 0)
  if (end <= start) {
    selectedResultText.value = ''
    return
  }
  const selected = String(resultData.result || '').slice(start, end).trim()
  selectedResultText.value = selected.slice(0, 1200)
}

const insertMarkdownImageAtSelection = (imageUrl: string) => {
  const content = String(resultData.result || '')
  const el = resultEditorRef.value
  const markdown = `\n\n![内容配图](${imageUrl})\n\n`
  if (el) {
    const start = Number(el.selectionStart || 0)
    const end = Number(el.selectionEnd || 0)
    if (end > start) {
      resultData.result = `${content.slice(0, end)}${markdown}${content.slice(end)}`
      return
    }
  }
  const selected = String(selectedResultText.value || '').trim()
  if (selected) {
    const idx = content.indexOf(selected)
    if (idx >= 0) {
      const tailStart = idx + selected.length
      resultData.result = `${content.slice(0, tailStart)}${markdown}${content.slice(tailStart)}`
      return
    }
  }
  resultData.result = `${content}\n\n![内容配图](${imageUrl})`
}

const generateInlineImageFromSelection = async () => {
  if (!resultData.article_id) {
    Message.warning('缺少文章ID，无法生成配图')
    return
  }
  const selected = String(selectedResultText.value || '').trim()
  if (!selected) {
    Message.warning('请先选中一段内容')
    return
  }
  inlineImageLoading.value = true
  try {
    const resp = await generateInlineIllustration(resultData.article_id, {
      selected_text: selected,
      context_text: String(resultData.result || ''),
      platform: String((resultData.options as any)?.platform || createForm.platform || 'wechat'),
      style: String((resultData.options as any)?.style || createForm.style || '专业深度'),
    })
    if (resp?.image_url) {
      insertMarkdownImageAtSelection(resp.image_url)
      if (!Array.isArray(resultData.images)) {
        resultData.images = []
      }
      resultData.images = [resp.image_url, ...(resultData.images || []).filter((x: any) => String(x || '').trim() && String(x || '').trim() !== resp.image_url)]
      Message.success('内容配图已生成并插入文稿')
    } else {
      Message.warning(resp?.image_notice || '未返回图片，已生成提示词')
    }
    if (resp?.image_notice) {
      resultData.image_notice = String(resp.image_notice || '')
    }
    if (resp?.plan) applyPlan(resp.plan)
  } catch (e: any) {
    handleActionableError(e)
  } finally {
    inlineImageLoading.value = false
  }
}

const captureDraftSelection = () => {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed) {
    selectedDraftText.value = ''
    return
  }
  const text = selection.toString().trim()
  selectedDraftText.value = text ? text.slice(0, 1200) : ''
}

const generateInlineImageFromDraftSelection = async () => {
  const draft = currentDraft.value
  if (!draft?.article_id) {
    Message.warning('缺少文章ID，无法生成配图')
    return
  }
  const selected = String(selectedDraftText.value || '').trim()
  if (!selected) {
    Message.warning('请先选中一段内容')
    return
  }
  draftInlineImageLoading.value = true
  try {
    const resp = await generateInlineIllustration(draft.article_id, {
      selected_text: selected,
      context_text: String(draft.content || ''),
      platform: String((draft.metadata as any)?.options?.platform || 'wechat'),
      style: String((draft.metadata as any)?.options?.style || '专业深度'),
    })
    if (resp?.image_url) {
      const content = String(draft.content || '')
      const markdown = `\n\n![内容配图](${resp.image_url})\n\n`
      const idx = content.indexOf(selected)
      const newContent = idx >= 0
        ? `${content.slice(0, idx + selected.length)}${markdown}${content.slice(idx + selected.length)}`
        : `${content}${markdown}`
      const updated = await updateDraft(draft.id, {
        title: draft.title,
        content: newContent,
        platform: draft.platform,
        mode: draft.mode,
      })
      currentDraft.value = updated
      const listIdx = drafts.value.findIndex((item) => item.id === updated.id)
      if (listIdx >= 0) drafts.value[listIdx] = updated
      selectedDraftText.value = ''
      Message.success('内容配图已生成并插入草稿')
    } else {
      Message.warning(resp?.image_notice || '未返回图片，已生成提示词')
    }
    if (resp?.plan) applyPlan(resp.plan)
  } catch (e: any) {
    handleActionableError(e)
  } finally {
    draftInlineImageLoading.value = false
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
    const mode = String(activeModeFromQuery.value || '').trim().toLowerCase() as ComposeMode
    if (mode === 'analyze' || mode === 'create' || mode === 'rewrite') {
      const linkedDraft = latestDraftByArticleMode.value[`${activeArticleId.value}:${mode}`]
      if (linkedDraft) {
        openDraftDetail(linkedDraft, false)
        return
      }
    }
    if (mode === 'create') {
      const targetArticle = articles.value.find((item: any) => String(item?.id || '') === activeArticleId.value)
      if (!targetArticle) return
      currentCreateArticle.value = targetArticle
      createForm.instruction = quickInstruction.value || ''
      createVisible.value = true
    }
  }
}

watch(resultVisible, (visible) => {
  if (!visible) {
    selectedResultText.value = ''
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
    selectedDraftText.value = ''
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
  runtimeSettings.value = await loadRuntimeSettings()
  initFiltersFromQuery()
  await loadComposeMeta()
  await fetchMps()
  await refreshAll()
  try {
    await recoverPendingComposeTasks()
  } catch (_) {}
  restoreFromRouteQuery()
})

onUnmounted(() => {
  for (const timer of composeTaskTimers.values()) {
    window.clearInterval(timer)
  }
  composeTaskTimers.clear()
  composeTaskPollingLocks.clear()
  Object.keys(runningActions).forEach((key) => delete runningActions[key])
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
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
}

.studio-display {
  min-width: 0;
}

.summary-row {
  margin-bottom: 14px;
}

.summary-card {
  min-height: 206px;
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

.result-editor-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-editor {
  width: 100%;
  min-height: 360px;
  resize: vertical;
  border: 1px solid #dce6f8;
  border-radius: 10px;
  padding: 12px;
  font-family: 'SFMono-Regular', 'JetBrains Mono', 'Menlo', monospace;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-1);
  background: #fbfdff;
}

.inline-illustration-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #dbeafe;
  background: #eff6ff;
  border-radius: 8px;
  padding: 8px 10px;
  color: #1e3a8a;
  font-size: 12px;
}

.draft-rendered {
  padding: 12px 16px;
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  line-height: 1.8;
  min-height: 200px;
  font-size: 14px;
  color: var(--color-text-1);
  user-select: text;
  cursor: text;
  overflow-wrap: break-word;

  :deep(img) {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 8px 0;
    border-radius: 4px;
  }

  :deep(h1), :deep(h2), :deep(h3) {
    margin: 16px 0 8px;
    font-weight: 600;
  }

  :deep(p) {
    margin: 6px 0;
  }

  :deep(ul), :deep(ol) {
    padding-left: 20px;
    margin: 6px 0;
  }

  :deep(blockquote) {
    border-left: 3px solid var(--color-border-3);
    padding-left: 12px;
    color: var(--color-text-3);
    margin: 8px 0;
  }

  :deep(code) {
    background: var(--color-fill-2);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 12px;
  }
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

.draft-delivery-log {
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--color-fill-1);
}

.draft-delivery-title {
  margin-bottom: 8px;
}

.draft-delivery-item + .draft-delivery-item {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--color-border-2);
}

.draft-delivery-message {
  margin-top: 4px;
  line-height: 1.6;
  color: var(--color-text-2);
}

.draft-delivery-extra {
  margin-top: 6px;
  max-height: 180px;
  overflow: auto;
  padding: 8px;
  border-radius: 6px;
  background: #f7f8fa;
  border: 1px solid var(--color-border-2);
  font-size: 12px;
  line-height: 1.5;
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
