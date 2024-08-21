new Vue({
    el: '#app',
    data() {
        return {
            availableTasks: [],
            jobs: [],
            newJob: {
                func: '',
                trigger: '',
                job_id: '',
                args: [],       // 任务位置参数
                kwargs: {},     // 任务关键字参数
                trigger_args: {} // 触发器特有字段
            },
            taskParams: {},
            editingJob: null,
            apiBaseUrl: 'http://192.168.2.78:8000'
        };
    },
    methods: {
        getDefaultTriggerArgs(triggerType) {
            if (triggerType === 'interval') {
                return {seconds: 0, minutes: 0, hours: 0};
            } else if (triggerType === 'cron') {
                return {second: 0, minute: 0, hour: 0, day: 1, month: 1, day_of_week: 0, year: null};
            } else {
                return {};
            }
        },
        formatDescription(description) {
            // 这里可以是你对描述进行格式化的逻辑
            return description.replace(/:\s*param\s*\w+\s*:/g, '').trim();
        },
        resetTriggerArgs() {
            const trigger = this.newJob.trigger;

            if (trigger === 'interval') {
                this.newJob.trigger_args = {
                    seconds: 0,
                    minutes: 0,
                    hours: 0,
                    days: 0,
                    weeks: 0
                };
            } else if (trigger === 'cron') {
                this.newJob.trigger_args = {
                    second: 0,
                    minute: 0,
                    hour: 0,
                    day: 1,
                    month: 1,
                    day_of_week: 0,
                    year: null
                };
            } else if (trigger === 'date') {
                this.newJob.trigger_args = {
                    run_date: ''
                };
            } else {
                this.newJob.trigger_args = {};
            }
        },
        fetchAvailableTasks() {
            fetch(`${this.apiBaseUrl}/available-tasks/`)
                .then(response => response.json())
                .then(data => {
                    this.availableTasks = data;
                })
                .catch(error => console.error('Error fetching available tasks:', error));
        },
        fetchJobs() {
            fetch(`${this.apiBaseUrl}/jobs/`)
                .then(response => response.json())
                .then(data => {
                    this.jobs = data;
                })
                .catch(error => console.error('Error fetching jobs:', error));
        },
        fetchTaskParams() {
            const funcName = this.newJob.func;
            const task = this.availableTasks.find(task => task.name === funcName);
            if (task) {
                this.taskParams = task.parameters;
            }
        },
        parseTriggerArgs(triggerType, params) {
            let trigger_args = {};
            if (triggerType === 'interval') {
                trigger_args = {
                    hours: params[0] || 0,
                    minutes: params[1] || 0,
                    seconds: params[2] || 0
                };
            } else if (triggerType === 'cron') {
                // 假设 cron 的参数顺序是 second, minute, hour, day, month, day_of_week, year
                trigger_args = {
                    second: params[0] || 0,
                    minute: params[1] || 0,
                    hour: params[2] || 0,
                    day: params[3] || 0,
                    month: params[4] || 0,
                    day_of_week: params[5] || 0,
                    year: params[6] || null // 可选
                };
            } else if (triggerType === 'date') {
                trigger_args = {
                    run_date: params[0] || ''
                };
            }

            return trigger_args;
        },
        validateJob() {
            const {trigger, job_id, trigger_args} = this.newJob;

            if (!this.newJob.func || !job_id || !trigger) {
                alert('请填写任务函数、任务ID和触发器类型');
                return false;
            }

            if (trigger === 'interval') {
                const {seconds, minutes, hours, days, weeks} = trigger_args;
                if (seconds === undefined && minutes === undefined && hours === undefined && days === undefined && weeks === undefined) {
                    alert('请至少填写一个间隔时间参数');
                    return false;
                }
            } else if (trigger === 'cron') {
                const {second, minute, hour, day, month, day_of_week, year} = trigger_args;
                if ([second, minute, hour, day, month, day_of_week, year].some(v => v !== undefined && isNaN(v))) {
                    alert('Cron参数必须是数字');
                    return false;
                }
            } else if (trigger === 'date') {
                const {run_date} = trigger_args;
                if (!run_date) {
                    alert('请填写运行日期');
                    return false;
                }
            }

            return true;
        },
        collectParams() {
            const args = [];
            const kwargs = {};

            for (const key in this.taskParams) {
                const paramType = this.taskParams[key].type;
                const value = this.newJob.kwargs[key];

                if (paramType === 'list') {
                    args.push(value);
                } else {
                    kwargs[key] = value;
                }
            }

            return {args, kwargs};
        },
        prepareTriggerArgs() {
            const {trigger} = this.newJob;
            let trigger_args = {};

            if (trigger === 'cron') {
                trigger_args = {
                    second: this.newJob.trigger_args.second || 0,
                    minute: this.newJob.trigger_args.minute || 0,
                    hour: this.newJob.trigger_args.hour || 0,
                    day: this.newJob.trigger_args.day || 0,
                    month: this.newJob.trigger_args.month || 0,
                    day_of_week: this.newJob.trigger_args.day_of_week || 0,
                    year: this.newJob.trigger_args.year || 0
                };
            } else if (trigger === 'interval') {
                trigger_args = {
                    seconds: this.newJob.trigger_args.seconds || 0,
                    minutes: this.newJob.trigger_args.minutes || 0,
                    hours: this.newJob.trigger_args.hours || 0,
                    days: this.newJob.trigger_args.days || 0,
                    weeks: this.newJob.trigger_args.weeks || 0
                };
            } else if (trigger === 'date') {
                trigger_args = {
                    run_date: this.newJob.trigger_args.run_date || ''
                };
            }

            return trigger_args;
        },
        createJob() {
            if (!this.validateJob()) return;

            const {args, kwargs} = this.collectParams();
            const trigger_args = this.prepareTriggerArgs();

            const jobData = {
                ...this.newJob,
                args,
                kwargs,
                trigger_args
            };

            fetch(`${this.apiBaseUrl}/add-job/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(jobData)
            })
                .then(response => response.json())
                .then(data => {
                    console.log('Job created:', data);
                    this.fetchJobs(); // 更新任务列表
                    this.resetNewJob(); // 重置新任务表单
                })
                .catch(error => console.error('Error creating job:', error));
        },
        updateJob() {
            if (!this.validateJob()) return;

            const {args, kwargs} = this.collectParams();
            const trigger_args = this.prepareTriggerArgs();

            const jobData = {
                ...this.newJob,
                args,
                kwargs,
                trigger_args
            };

            fetch(`${this.apiBaseUrl}/update-job/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(jobData)
            })
                .then(response => response.json())
                .then(data => {
                    console.log('Job updated:', data);
                    this.fetchJobs(); // 更新任务列表
                    this.resetNewJob(); // 重置表单
                    this.editingJob = null; // 清除编辑状态
                })
                .catch(error => console.error('Error updating job:', error));
        },
        editJob(job) {
            // 进入编辑模式
            this.editingJob = true;

            // 深拷贝任务数据
            this.newJob = JSON.parse(JSON.stringify(job));

            // 获取当前任务的参数
            this.fetchTaskParams();

            // 填充任务函数参数
            if (job.args && job.args.length > 0) {
                // 假设 taskParams 是按照顺序来的
                const paramNames = Object.keys(this.taskParams);
                job.args.forEach((argValue, index) => {
                    if (paramNames[index]) {
                        this.newJob.kwargs[paramNames[index]] = argValue;
                    }
                });
            }

            // 合并现有的 kwargs
            if (job.kwargs) {
                this.newJob.kwargs = {...this.newJob.kwargs, ...job.kwargs};
            }

            // 设置任务ID
            this.newJob.job_id = job.id || '';

            // 解析并设置触发器类型和参数
            const triggerTypeMatch = job.trigger.match(/(\w+)\[(.*)\]/);
            if (triggerTypeMatch) {
                this.newJob.trigger = triggerTypeMatch[1]; // 触发器类型
                const triggerParams = triggerTypeMatch[2].split(':'); // 分割参数
                this.newJob.trigger_args = this.parseTriggerArgs(this.newJob.trigger, triggerParams);
            } else {
                this.newJob.trigger = job.trigger || '';
                this.newJob.trigger_args = {};
            }


        },
        deleteJob(job_id) {
            fetch(`${this.apiBaseUrl}/remove-job/${job_id}`, {
                method: 'GET'
            })
                .then(response => response.json())
                .then(data => {
                    console.log('Job deleted:', data);
                    this.fetchJobs(); // 更新任务列表
                })
                .catch(error => console.error('Error deleting job:', error));
        },
        pauseJob(job_id) {
            fetch(`${this.apiBaseUrl}/pause-job/${job_id}`, {
                method: 'GET'
            })
                .then(response => response.json())
                .then(data => {
                    console.log('Job paused:', data);
                    this.fetchJobs(); // 更新任务列表
                })
                .catch(error => console.error('Error pausing job:', error));
        },
        resumeJob(job_id) {
            fetch(`${this.apiBaseUrl}/resume-job/${job_id}`, {
                method: 'GET'
            })
                .then(response => response.json())
                .then(data => {
                    console.log('Job resumed:', data);
                    this.fetchJobs(); // 更新任务列表
                })
                .catch(error => console.error('Error resuming job:', error));
        },
        runJob(job_id) {
            fetch(`${this.apiBaseUrl}/run-job-now/?job_id=${job_id}`, {
                method: 'POST'
            })
                .then(response => response.json())
                .then(data => {
                    console.log('Job Running:', data);
                    this.fetchJobs(); // 更新任务列表
                })
                .catch(error => console.error('Error running job:', error));
        },
        resetNewJob() {
            this.newJob = {
                func: '',
                trigger: '',
                job_id: '',
                args: [],
                kwargs: {},
                trigger_args: {} // 触发器特有字段
            };
            this.taskParams = {};
        },
        setApiBaseUrl() {
            const inputUrl = prompt("请输入API基础地址", this.apiBaseUrl);
            if (inputUrl) {
                this.apiBaseUrl = inputUrl;
                this.fetchAvailableTasks(); // 重新获取任务列表
                this.fetchJobs(); // 重新获取任务列表
            }
        },
        formatJobArgs(args) {
            return Object.entries(args).map(([key, value]) => `${key}: ${value}`).join(', ');
        },

    },
    watch: {

        'newJob.func': function (newFunc) {
            this.fetchTaskParams();
        },
        'newJob.trigger': function (newTrigger) {
            // 当触发器类型更改时，重置 trigger_args
            this.newJob.trigger_args = this.getDefaultTriggerArgs(newTrigger);
        },

    },
    mounted() {
        this.fetchAvailableTasks();
        this.fetchJobs();
    }
});
