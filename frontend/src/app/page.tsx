"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  BookOpen,
  Check,
  Database,
  Edit3,
  Download,
  FileUp,
  FolderOpen,
  KeyRound,
  Loader2,
  LogOut,
  PanelLeft,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Shield,
  UserPlus,
  UsersRound,
  X
} from "lucide-react";
import { apiRequest } from "@/lib/api";
import type {
  ActivityLog,
  ApprovedResource,
  CandidateResource,
  Course,
  EvaluationReport,
  ExportHistory,
  Job,
  Role,
  SourceConfig,
  Topic,
  User
} from "@/types";

const categories = [
  "Books",
  "Journal Articles",
  "Newspaper Articles",
  "Industry Reports",
  "Workshops & Trainings",
  "Software & Tools"
];

const sessionStorageKey = "rcaabut-dashboard-session";

const sidebarRoutes = [
  { label: "Dashboard", href: "/dashboard", view: "dashboard", icon: PanelLeft },
  { label: "User Management", href: "/user-management", view: "users", icon: UsersRound, superAdminOnly: true },
  { label: "Courses", href: "/courses", view: "courses", icon: BookOpen },
  { label: "Upload Compact", href: "/upload-compact", view: "upload", icon: FileUp },
  { label: "Reports", href: "/reports", view: "reports", icon: BarChart3 },
  { label: "Settings", href: "/settings", view: "settings", icon: Settings2 }
];

type DashboardView = "dashboard" | "users" | "courses" | "upload" | "reports" | "settings";

const viewTitles: Record<DashboardView, { eyebrow: string; title: string; description: string }> = {
  dashboard: {
    eyebrow: "Repository Overview",
    title: "Dashboard",
    description: "Monitor repository activity, course extraction status, approvals, and export readiness from one calm workspace."
  },
  users: {
    eyebrow: "Super Admin",
    title: "User Management",
    description: "Create library staff accounts, adjust roles, reset passwords, and keep account access tidy."
  },
  courses: {
    eyebrow: "Course Repository",
    title: "Courses",
    description: "Browse uploaded compacts, select a course, edit metadata, review topics, and curate approved records."
  },
  upload: {
    eyebrow: "Upload Compact",
    title: "Upload a course compact",
    description: "Start a new course extraction by uploading a PDF compact for topic review and resource generation."
  },
  reports: {
    eyebrow: "Reports",
    title: "Reports and exports",
    description: "Review prototype metrics, activity history, export records, and generated files."
  },
  settings: {
    eyebrow: "Settings",
    title: "Account and sources",
    description: "Change your password and manage discovery connector availability."
  }
};

function pathToView(pathname: string, role?: Role): DashboardView {
  const pathMap: Record<string, DashboardView> = {
    "/": "dashboard",
    "/dashboard": "dashboard",
    "/user-management": "users",
    "/courses": "courses",
    "/upload-compact": "upload",
    "/reports": "reports",
    "/settings": "settings"
  };
  const value = pathMap[pathname] || "dashboard";
  if (value === "users" && role !== "super_admin") {
    return "dashboard";
  }
  return value;
}

type CourseDetail = {
  course: Course;
  topics: Topic[];
  candidates: CandidateResource[];
  approved_resources: ApprovedResource[];
};

type Session = {
  access_token: string;
  user: User;
};

type UserPatch = {
  full_name?: string;
  password?: string;
  role?: Role;
  is_active?: boolean;
};

const statusLabels: Record<string, string> = {
  uploaded: "Uploaded",
  extracted: "Extracted",
  topics_reviewed: "Topics Reviewed",
  under_review: "Under Review",
  resources_generated: "Resources Generated",
  exported: "Exported",
  archived: "Archived"
};

function statusLabel(status: string) {
  return statusLabels[status] || status.replaceAll("_", " ");
}

function groupByTopic<T extends { topic_id: number }>(rows: T[]) {
  return rows.reduce<Record<number, T[]>>((grouped, row) => {
    grouped[row.topic_id] = grouped[row.topic_id] || [];
    grouped[row.topic_id].push(row);
    return grouped;
  }, {});
}

function roleLabel(role: string) {
  return role === "super_admin" ? "Super Admin" : "Library Staff";
}

function exportContentType(exportType: string) {
  if (exportType === "csv") {
    return "text/csv;charset=utf-8";
  }
  if (exportType === "html") {
    return "text/html;charset=utf-8";
  }
  return "application/json";
}

export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [loginEmail, setLoginEmail] = useState("admin@rcaabut.local");
  const [loginPassword, setLoginPassword] = useState("ChangeMe123!");
  const [message, setMessage] = useState("Sign in with the seeded Super Admin account to begin.");
  const [booting, setBooting] = useState(true);
  const [busy, setBusy] = useState(false);
  const [activeView, setActiveView] = useState<DashboardView>("dashboard");
  const [courses, setCourses] = useState<Course[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [userPasswords, setUserPasswords] = useState<Record<number, string>>({});
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [detail, setDetail] = useState<CourseDetail | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [activity, setActivity] = useState<ActivityLog[]>([]);
  const [exports, setExports] = useState<ExportHistory[]>([]);
  const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null);
  const [sources, setSources] = useState<SourceConfig[]>([]);
  const [newUser, setNewUser] = useState({
    full_name: "",
    email: "",
    password: "",
    role: "library_staff"
  });
  const [manualResource, setManualResource] = useState({
    topic_id: "",
    category: "Books",
    title: "",
    authors: "",
    year: "",
    url: "",
    note: ""
  });
  const [newTopic, setNewTopic] = useState({
    week_number: "",
    module_title: "",
    topic_title: "",
    subtopics: ""
  });
  const [accountPassword, setAccountPassword] = useState({
    current_password: "",
    new_password: "",
    confirm_password: ""
  });

  const token = session?.access_token;
  const selectedCourse = useMemo(
    () => (detail?.course.id === selectedCourseId ? detail.course : null),
    [detail?.course, selectedCourseId]
  );
  const searchableTopics = useMemo(() => detail?.topics.filter((topic) => topic.is_searchable) || [], [detail?.topics]);
  const hasSearchableTopics = searchableTopics.length > 0;
  const hasConfirmedTopics = selectedCourse
    ? ["topics_reviewed", "resources_generated", "exported"].includes(selectedCourse.status)
    : false;
  const isArchivedCourse = selectedCourse?.status === "archived";
  const canGenerateResources = !isArchivedCourse && hasConfirmedTopics && hasSearchableTopics;
  const generateResourcesTitle = isArchivedCourse
    ? "Restore this course before generating resources"
    : !hasConfirmedTopics
    ? "Confirm topics before generating resources"
    : hasSearchableTopics
      ? "Generate resources"
      : "Mark at least one teaching topic as searchable before generating resources";
  const candidatesByTopic = useMemo(() => groupByTopic(detail?.candidates || []), [detail?.candidates]);
  const approvedByTopic = useMemo(() => groupByTopic(detail?.approved_resources || []), [detail?.approved_resources]);
  const hasApprovedResources = (detail?.approved_resources.length || 0) > 0;
  const exportTitle = isArchivedCourse
    ? "Restore this course before exporting"
    : hasApprovedResources
      ? "Export approved records"
      : "Approve at least one resource before exporting";
  const stats = useMemo(() => {
    const approved = detail?.approved_resources.length || 0;
    const pending = detail?.candidates.filter((item) => item.status === "pending" || item.status === "edited").length || 0;
    return {
      courses: courses.length,
      topics: detail?.topics.length || 0,
      pending,
      approved
    };
  }, [courses.length, detail]);

  useEffect(() => {
    function syncView() {
      setActiveView(pathToView(window.location.pathname, session?.user.role));
    }

    syncView();
    window.addEventListener("popstate", syncView);
    return () => window.removeEventListener("popstate", syncView);
  }, [session?.user.role]);

  const currentView = session ? viewTitles[activeView] : null;

  useEffect(() => {
    if (!manualResource.topic_id) {
      return;
    }
    const selectedTopicId = Number(manualResource.topic_id);
    if (!searchableTopics.some((topic) => topic.id === selectedTopicId)) {
      setManualResource((current) => ({ ...current, topic_id: "" }));
    }
  }, [manualResource.topic_id, searchableTopics]);

  async function runDashboardAction(task: () => Promise<void>, fallbackMessage: string, options: { showBusy?: boolean } = {}) {
    if (options.showBusy) {
      setBusy(true);
    }
    try {
      await task();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : fallbackMessage);
    } finally {
      if (options.showBusy) {
        setBusy(false);
      }
    }
  }

  const refreshReports = useCallback(async () => {
    if (!token) {
      return;
    }
    const [activityPayload, exportsPayload, evaluationPayload] = await Promise.all([
      apiRequest<{ activity: ActivityLog[] }>("/reports/activity", {}, token),
      apiRequest<{ exports: ExportHistory[] }>("/reports/exports", {}, token),
      apiRequest<EvaluationReport>("/reports/evaluation", {}, token)
    ]);
    setActivity(activityPayload.activity);
    setExports(exportsPayload.exports);
    setEvaluation(evaluationPayload);
  }, [token]);

  const refreshSources = useCallback(async () => {
    if (!token) {
      return;
    }
    const payload = await apiRequest<{ sources: SourceConfig[] }>("/sources", {}, token);
    setSources(payload.sources);
  }, [token]);

  const refreshUsers = useCallback(async () => {
    if (!token || session?.user.role !== "super_admin") {
      return;
    }
    const payload = await apiRequest<{ users: User[] }>("/users", {}, token);
    setUsers(payload.users);
  }, [session?.user.role, token]);

  useEffect(() => {
    if (activeView === "users") {
      refreshUsers().catch((error) => setMessage(error instanceof Error ? error.message : "Could not refresh users."));
    }
  }, [activeView, refreshUsers]);

  useEffect(() => {
    const saved = window.localStorage.getItem(sessionStorageKey);
    if (!saved) {
      setBooting(false);
      return;
    }
    let parsed: Session;
    try {
      parsed = JSON.parse(saved) as Session;
    } catch {
      window.localStorage.removeItem(sessionStorageKey);
      setBooting(false);
      return;
    }
    let cancelled = false;
    async function restoreSession() {
      try {
        await apiRequest<User>("/auth/me", {}, parsed.access_token);
        const [coursePayload, activityPayload, exportsPayload, evaluationPayload, sourcesPayload] = await Promise.all([
          apiRequest<{ courses: Course[] }>("/courses", {}, parsed.access_token),
          apiRequest<{ activity: ActivityLog[] }>("/reports/activity", {}, parsed.access_token),
          apiRequest<{ exports: ExportHistory[] }>("/reports/exports", {}, parsed.access_token),
          apiRequest<EvaluationReport>("/reports/evaluation", {}, parsed.access_token),
          apiRequest<{ sources: SourceConfig[] }>("/sources", {}, parsed.access_token)
        ]);
        if (cancelled) {
          return;
        }
        setSession(parsed);
        setCourses(coursePayload.courses);
        setActivity(activityPayload.activity);
        setExports(exportsPayload.exports);
        setEvaluation(evaluationPayload);
        setSources(sourcesPayload.sources);
        let courseLoaded = true;
        if (coursePayload.courses[0]) {
          courseLoaded = await loadCourse(coursePayload.courses[0].id, parsed.access_token);
        }
        if (parsed.user.role === "super_admin") {
          const userPayload = await apiRequest<{ users: User[] }>("/users", {}, parsed.access_token);
          if (!cancelled) {
            setUsers(userPayload.users);
          }
        }
        if (!cancelled && courseLoaded) {
          setMessage(`Welcome back, ${parsed.user.full_name}.`);
        } else if (!cancelled) {
          setMessage(`Welcome back, ${parsed.user.full_name}. Select a course from the refreshed list or upload a new compact.`);
        }
      } catch {
        window.localStorage.removeItem(sessionStorageKey);
      } finally {
        if (!cancelled) {
          setBooting(false);
        }
      }
    }
    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshCourses = useCallback(async (accessToken = token) => {
    if (!accessToken) {
      return [];
    }
    const payload = await apiRequest<{ courses: Course[] }>("/courses", {}, accessToken);
    setCourses(payload.courses);
    return payload.courses;
  }, [token]);

  const loadCourse = useCallback(
    async (courseId: number, accessToken = token) => {
      if (!accessToken) {
        return false;
      }
      try {
        const payload = await apiRequest<CourseDetail>(`/courses/${courseId}`, {}, accessToken);
        setDetail(payload);
        setSelectedCourseId(courseId);
        return true;
      } catch (error) {
        setDetail(null);
        setSelectedCourseId(null);
        try {
          await refreshCourses(accessToken);
        } catch {
          setCourses([]);
        }
        setMessage(error instanceof Error ? `Could not load that course: ${error.message}` : "Could not load that course.");
        return false;
      }
    },
    [refreshCourses, token]
  );

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = await apiRequest<Session>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: loginEmail, password: loginPassword })
      });
      setSession(payload);
      window.localStorage.setItem(sessionStorageKey, JSON.stringify(payload));
      setMessage(`Welcome, ${payload.user.full_name}.`);
      const coursePayload = await apiRequest<{ courses: Course[] }>("/courses", {}, payload.access_token);
      setCourses(coursePayload.courses);
      let courseLoaded = true;
      if (coursePayload.courses[0]) {
        courseLoaded = await loadCourse(coursePayload.courses[0].id, payload.access_token);
      }
      if (payload.user.role === "super_admin") {
        const userPayload = await apiRequest<{ users: User[] }>("/users", {}, payload.access_token);
        setUsers(userPayload.users);
      }
      const [activityPayload, exportsPayload, evaluationPayload, sourcesPayload] = await Promise.all([
        apiRequest<{ activity: ActivityLog[] }>("/reports/activity", {}, payload.access_token),
        apiRequest<{ exports: ExportHistory[] }>("/reports/exports", {}, payload.access_token),
        apiRequest<EvaluationReport>("/reports/evaluation", {}, payload.access_token),
        apiRequest<{ sources: SourceConfig[] }>("/sources", {}, payload.access_token)
      ]);
      setActivity(activityPayload.activity);
      setExports(exportsPayload.exports);
      setEvaluation(evaluationPayload);
      setSources(sourcesPayload.sources);
      if (!courseLoaded) {
        setMessage("Signed in. Select a course from the refreshed list or upload a new compact.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  async function pollJob(jobId: number) {
    if (!token) {
      return;
    }
    let done = false;
    while (!done) {
      const payload = await apiRequest<Job>(`/jobs/${jobId}`, {}, token);
      setJob(payload);
      done = payload.status === "completed" || payload.status === "failed";
      if (!done) {
        await new Promise((resolve) => setTimeout(resolve, 1200));
      }
    }
    await refreshCourses();
    const finalJob = await apiRequest<Job>(`/jobs/${jobId}`, {}, token);
    if (finalJob.course_id) {
      await loadCourse(finalJob.course_id);
    }
    await refreshReports();
  }

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile || !token) {
      setMessage("Choose a course compact PDF first.");
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      form.append("compact_pdf", selectedFile);
      const payload = await apiRequest<{ compact_id: number; job_id: number; status: string }>(
        "/compacts/upload",
        { method: "POST", body: form },
        token
      );
      setMessage("Compact uploaded. Extracting course topics now.");
      await pollJob(payload.job_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }
    setBusy(true);
    try {
      await apiRequest<{ user: User }>("/users", { method: "POST", body: JSON.stringify(newUser) }, token);
      setNewUser({ full_name: "", email: "", password: "", role: "library_staff" });
      setMessage("User created.");
      await refreshUsers();
      await refreshReports();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "User creation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function updateUser(userId: number, updates: UserPatch) {
    if (!token) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(`/users/${userId}`, { method: "PATCH", body: JSON.stringify(updates) }, token);
      await refreshUsers();
      await refreshReports();
      setMessage("User updated.");
    }, "User update failed.");
  }

  async function resetUserPassword(userId: number) {
    const password = userPasswords[userId]?.trim();
    if (!password) {
      setMessage("Enter a new password first.");
      return;
    }
    if (password.length < 8) {
      setMessage("Password must be at least 8 characters.");
      return;
    }
    await updateUser(userId, { password });
    setUserPasswords((current) => ({ ...current, [userId]: "" }));
    setMessage("User password reset.");
  }

  async function changeOwnPassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }
    if (accountPassword.new_password.length < 8) {
      setMessage("New password must be at least 8 characters.");
      return;
    }
    if (accountPassword.new_password !== accountPassword.confirm_password) {
      setMessage("New password and confirmation do not match.");
      return;
    }
    await runDashboardAction(
      async () => {
        await apiRequest(
          "/auth/change-password",
          {
            method: "POST",
            body: JSON.stringify({
              current_password: accountPassword.current_password,
              new_password: accountPassword.new_password
            })
          },
          token
        );
        setAccountPassword({ current_password: "", new_password: "", confirm_password: "" });
        setMessage("Your password has been changed.");
      },
      "Password change failed.",
      { showBusy: true }
    );
  }

  async function updateSource(source: SourceConfig) {
    if (!token) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(
        `/sources/${source.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            display_name: source.display_name,
            source_type: source.source_type,
            base_url: source.base_url,
            is_enabled: source.is_enabled,
            notes: source.notes
          })
        },
        token
      );
      await refreshSources();
      await refreshReports();
      setMessage("Source setting updated.");
    }, "Source update failed.");
  }

  function signOut() {
    window.localStorage.removeItem(sessionStorageKey);
    setSession(null);
    setCourses([]);
    setUsers([]);
    setDetail(null);
    setSelectedCourseId(null);
    setActivity([]);
    setExports([]);
    setEvaluation(null);
    setSources([]);
    setMessage("Signed out.");
  }

  async function updateTopic(topic: Topic) {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      const payload = {
        module_number: topic.module_number,
        module_title: topic.module_title,
        week_number: topic.week_number,
        topic_title: topic.topic_title,
        subtopics: topic.subtopics,
        outcomes: topic.outcomes,
        is_searchable: topic.is_searchable
      };
      await apiRequest(`/courses/${selectedCourseId}/topics/${topic.id}`, { method: "PATCH", body: JSON.stringify(payload) }, token);
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage("Topic updated.");
    }, "Topic update failed.");
  }

  async function addTopic(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(
        `/courses/${selectedCourseId}/topics`,
        {
          method: "POST",
          body: JSON.stringify({
            week_number: newTopic.week_number ? Number(newTopic.week_number) : null,
            module_number: null,
            module_title: newTopic.module_title || null,
            topic_title: newTopic.topic_title,
            subtopics: newTopic.subtopics
              .split(";")
              .map((item) => item.trim())
              .filter(Boolean),
            outcomes: [],
            is_searchable: true
          })
        },
        token
      );
      setNewTopic({ week_number: "", module_title: "", topic_title: "", subtopics: "" });
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage("Topic added.");
    }, "Topic add failed.");
  }

  async function deleteTopic(topicId: number) {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(`/courses/${selectedCourseId}/topics/${topicId}`, { method: "DELETE" }, token);
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage("Topic deleted.");
    }, "Topic delete failed.");
  }

  async function updateCandidate(candidate: CandidateResource) {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(
        `/courses/${selectedCourseId}/candidates/${candidate.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            category: candidate.category,
            title: candidate.title,
            authors: candidate.authors,
            year: candidate.year,
            abstract: candidate.abstract,
            url: candidate.url,
            match_reason: candidate.match_reason
          })
        },
        token
      );
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage("Candidate updated.");
    }, "Candidate update failed.");
  }

  async function updateCourse(course: Course) {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(
        `/courses/${selectedCourseId}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            course_code: course.course_code,
            course_title: course.course_title,
            college: course.college,
            department: course.department,
            programme: course.programme,
            level: course.level,
            semester: course.semester,
            session: course.session,
            lecturers: course.lecturers,
            description: course.description
          })
        },
        token
      );
      await refreshCourses();
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage("Course metadata updated.");
    }, "Course metadata update failed.");
  }

  async function archiveOrRestoreCourse() {
    if (!token || !selectedCourseId || !selectedCourse) {
      return;
    }
    await runDashboardAction(async () => {
      const action = selectedCourse.status === "archived" ? "restore" : "archive";
      await apiRequest(`/courses/${selectedCourseId}/${action}`, { method: "POST" }, token);
      await refreshCourses();
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage(action === "archive" ? "Course archived." : "Course restored.");
    }, "Course archive/restore failed.");
  }

  async function confirmTopics() {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(`/courses/${selectedCourseId}/topics/confirm`, { method: "POST" }, token);
      await refreshCourses();
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage("Topics confirmed. You can generate resources now.");
    }, "Topic confirmation failed.");
  }

  async function generateResources() {
    if (!token || !selectedCourseId) {
      return;
    }
    setBusy(true);
    try {
      const payload = await apiRequest<{ job_id: number }>(
        `/courses/${selectedCourseId}/generate-resources`,
        { method: "POST" },
        token
      );
      setMessage("Generating top 5 resources per topic.");
      await pollJob(payload.job_id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Resource generation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function reviewCandidate(candidate: CandidateResource, action: "approve" | "reject") {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(
        `/courses/${selectedCourseId}/candidates/${candidate.id}/review`,
        {
          method: "POST",
          body: JSON.stringify({
            action,
            category: candidate.category,
            title: candidate.title,
            authors: candidate.authors,
            year: candidate.year,
            url: candidate.url
          })
        },
        token
      );
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage(action === "approve" ? "Resource approved." : "Resource rejected.");
    }, action === "approve" ? "Resource approval failed." : "Resource rejection failed.");
  }

  async function addManualResource(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(
        `/courses/${selectedCourseId}/manual-resources`,
        {
          method: "POST",
          body: JSON.stringify({
            topic_id: Number(manualResource.topic_id),
            category: manualResource.category,
            title: manualResource.title,
            authors: manualResource.authors
              .split(";")
              .map((item) => item.trim())
              .filter(Boolean),
            year: manualResource.year ? Number(manualResource.year) : null,
            url: manualResource.url || null,
            note: manualResource.note || null
          })
        },
        token
      );
      setManualResource({ topic_id: "", category: "Books", title: "", authors: "", year: "", url: "", note: "" });
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage("Manual resource added.");
    }, "Manual resource add failed.");
  }

  async function updateApprovedResource(resource: ApprovedResource) {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(
        `/courses/${selectedCourseId}/approved-resources/${resource.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            category: resource.category,
            title: resource.title,
            authors: resource.authors,
            year: resource.year,
            url: resource.url,
            note: resource.note
          })
        },
        token
      );
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage("Approved resource updated.");
    }, "Approved resource update failed.");
  }

  async function deleteApprovedResource(resourceId: number) {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(async () => {
      await apiRequest(`/courses/${selectedCourseId}/approved-resources/${resourceId}`, { method: "DELETE" }, token);
      await loadCourse(selectedCourseId);
      await refreshReports();
      setMessage("Approved resource removed.");
    }, "Approved resource removal failed.");
  }

  async function exportJson() {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(
      async () => {
        const payload = await apiRequest<{ payload: unknown }>(`/courses/${selectedCourseId}/exports/json`, { method: "POST" }, token);
        const blob = new Blob([JSON.stringify(payload.payload, null, 2)], { type: "application/json" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `${selectedCourse?.course_code || "course"}_rcaabut_export.json`;
        link.click();
        URL.revokeObjectURL(link.href);
        await refreshCourses();
        await refreshReports();
        setMessage("JSON export downloaded.");
      },
      "JSON export failed.",
      { showBusy: true }
    );
  }

  async function exportCsv() {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(
      async () => {
        const csv = await apiRequest<string>(`/courses/${selectedCourseId}/exports/csv`, {}, token);
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `${selectedCourse?.course_code || "course"}_rcaabut_export.csv`;
        link.click();
        URL.revokeObjectURL(link.href);
        await refreshCourses();
        await refreshReports();
        setMessage("CSV export downloaded.");
      },
      "CSV export failed.",
      { showBusy: true }
    );
  }

  async function exportHtml() {
    if (!token || !selectedCourseId) {
      return;
    }
    await runDashboardAction(
      async () => {
        const html = await apiRequest<string>(`/courses/${selectedCourseId}/exports/html`, {}, token);
        const blob = new Blob([html], { type: "text/html;charset=utf-8" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `${selectedCourse?.course_code || "course"}_rcaabut_resources.html`;
        link.click();
        URL.revokeObjectURL(link.href);
        await refreshCourses();
        await refreshReports();
        setMessage("HTML export downloaded.");
      },
      "HTML export failed.",
      { showBusy: true }
    );
  }

  async function downloadStoredExport(item: ExportHistory) {
    if (!token) {
      return;
    }
    await runDashboardAction(
      async () => {
        const content = await apiRequest<string>(`/reports/exports/${item.id}/download`, {}, token);
        const blob = new Blob([content], { type: exportContentType(item.export_type) });
        const link = document.createElement("a");
        const courseCode = item.course.split(" - ")[0] || "course";
        link.href = URL.createObjectURL(blob);
        link.download = `${courseCode}_stored_rcaabut_export.${item.export_type}`;
        link.click();
        URL.revokeObjectURL(link.href);
        setMessage(`${item.export_type.toUpperCase()} export downloaded from history.`);
      },
      "Stored export download failed.",
      { showBusy: true }
    );
  }

  if (booting) {
    return <LoadingShell />;
  }

  if (!session) {
    return (
      <main className="grid min-h-screen place-items-center bg-library-paper px-5 py-8">
        <section className="w-full max-w-[430px]">
          <div className="mb-8 flex justify-center">
            <BrandLogo />
          </div>
          <form onSubmit={handleLogin} className="panel p-6 md:p-7">
            <div className="mb-6 flex items-center justify-between border-b border-library-line pb-5">
              <div>
                <p className="label">Secure Access</p>
                <h2 className="mt-1 text-2xl font-extrabold text-library-ink">Sign in</h2>
              </div>
              <div className="grid h-11 w-11 place-items-center rounded-full bg-library-purple/10 text-library-purple">
                <Shield size={20} />
              </div>
            </div>
            <label className="label" htmlFor="email">
              Email
            </label>
            <input id="email" className="control mt-2" value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} />
            <label className="label mt-4 block" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="control mt-2"
              value={loginPassword}
              onChange={(event) => setLoginPassword(event.target.value)}
            />
            <button className="btn-primary mt-6 w-full" disabled={busy}>
              {busy ? <Loader2 className="animate-spin" size={18} /> : <Shield size={18} />}
              Sign in
            </button>
            <p className="mt-4 rounded-lg bg-library-paper px-3 py-2 text-sm text-library-muted" aria-live="polite">
              {message}
            </p>
          </form>
        </section>
      </main>
    );
  }

  const visibleRoutes = sidebarRoutes.filter((route) => !route.superAdminOnly || session.user.role === "super_admin");

  return (
    <main className="min-h-screen bg-library-paper lg:grid lg:grid-cols-[304px_minmax(0,1fr)]">
      <aside className="border-b border-library-line bg-white px-4 py-5 shadow-soft lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-b-0 lg:border-r lg:px-5">
        <div className="flex min-h-full flex-col gap-5">
          <BrandLogo compact />

          <nav className="space-y-1" aria-label="Dashboard routes">
            {visibleRoutes.map((route) => {
              const Icon = route.icon;
              const isActive = activeView === route.view;
              return (
                <a
                  key={route.href}
                  href={route.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-bold transition ${
                    isActive
                      ? "bg-library-purple/10 text-library-purple"
                      : "text-library-muted hover:bg-library-purple/10 hover:text-library-purple"
                  }`}
                >
                  <Icon size={17} />
                  <span>{route.label}</span>
                </a>
              );
            })}
          </nav>

          <button className="btn-secondary mt-auto w-full justify-start" onClick={signOut}>
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      </aside>

      <div className="min-w-0 px-4 py-5 md:px-6 lg:px-8">
        <section className="mx-auto max-w-[1180px] space-y-5">
          {currentView ? <PageHeader eyebrow={currentView.eyebrow} title={currentView.title} description={currentView.description} /> : null}

          {activeView === "dashboard" ? (
            <>
              <section className="panel overflow-hidden">
                <div className="grid gap-0 border-b border-library-line md:grid-cols-4">
                  <StatCard icon={<Database size={18} />} label="Courses" value={stats.courses} />
                  <StatCard icon={<BookOpen size={18} />} label="Topics" value={stats.topics} />
                  <StatCard icon={<Settings2 size={18} />} label="Pending Review" value={stats.pending} />
                  <StatCard icon={<UsersRound size={18} />} label="Approved" value={stats.approved} />
                </div>
                <div className="grid gap-5 p-5 md:grid-cols-2 md:p-6">
                  <div className="rounded-lg border border-library-line bg-white p-5">
                    <p className="label">Next action</p>
                    <h3 className="mt-2 text-lg font-extrabold">Upload or review courses</h3>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <a className="btn-primary" href="/upload-compact">
                        <FileUp size={16} />
                        Upload Compact
                      </a>
                      <a className="btn-secondary" href="/courses">
                        <BookOpen size={16} />
                        View Courses
                      </a>
                    </div>
                  </div>
                  <div className="rounded-lg border border-library-line bg-white p-5">
                    <p className="label">Session</p>
                    <h3 className="mt-2 text-lg font-extrabold">{roleLabel(session.user.role)}</h3>
                    <p className="mt-2 text-sm leading-6 text-library-muted">{session.user.full_name}</p>
                  </div>
                </div>
              </section>
              <section className="grid gap-5 lg:grid-cols-2">
                <ActivityPanel activity={activity} />
                <ExportPanel exports={exports} onDownload={downloadStoredExport} />
              </section>
            </>
          ) : null}

          {activeView === "upload" ? (
            <form onSubmit={handleUpload} className="panel p-6">
              <p className="label">Upload Compact</p>
              <label className="mt-4 flex min-h-[260px] cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-library-purple/35 bg-library-purple/5 px-4 py-10 text-center transition hover:border-library-purple">
                <FileUp className="mb-3 text-library-purple" size={34} />
                <span className="text-base font-extrabold text-library-ink">{selectedFile?.name || "Choose PDF"}</span>
                <span className="mt-1 text-sm text-library-muted">Course compact only</span>
                <input
                  type="file"
                  accept="application/pdf"
                  className="sr-only"
                  onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                />
              </label>
              <button className="btn-primary mt-4" disabled={busy || !selectedFile}>
                {busy ? <Loader2 className="animate-spin" size={16} /> : <FileUp size={16} />}
                Upload & Extract
              </button>
            </form>
          ) : null}

          {activeView === "users" && session.user.role === "super_admin" ? (
            <section className="grid gap-5 lg:grid-cols-[420px_1fr]">
              <form onSubmit={handleCreateUser} className="panel p-5">
                <p className="label">Create User</p>
                <h2 className="mt-1 text-xl font-extrabold">New account</h2>
                <input className="control mt-4" placeholder="Full name" value={newUser.full_name} onChange={(event) => setNewUser({ ...newUser, full_name: event.target.value })} />
                <input className="control mt-3" placeholder="Email" value={newUser.email} onChange={(event) => setNewUser({ ...newUser, email: event.target.value })} />
                <input className="control mt-3" placeholder="Password" type="password" value={newUser.password} onChange={(event) => setNewUser({ ...newUser, password: event.target.value })} />
                <select className="control mt-3" value={newUser.role} onChange={(event) => setNewUser({ ...newUser, role: event.target.value })}>
                  <option value="library_staff">Library Staff</option>
                  <option value="super_admin">Super Admin</option>
                </select>
                <button className="btn-gold mt-4 w-full" disabled={busy}>
                  {busy ? <Loader2 className="animate-spin" size={16} /> : <UserPlus size={16} />}
                  Create
                </button>
              </form>
              <div className="panel p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="label">Accounts</p>
                    <h2 className="mt-1 text-xl font-extrabold">User Management</h2>
                    <p className="mt-1 text-sm text-library-muted">{users.length} account{users.length === 1 ? "" : "s"} found</p>
                  </div>
                  <button className="btn-secondary" type="button" onClick={() => refreshUsers()} disabled={busy}>
                    <RefreshCw size={16} />
                    Refresh
                  </button>
                </div>
                <div className="mt-4 grid gap-3">
                  {users.map((user) => (
                    <UserManagementRow
                      key={user.id}
                      user={user}
                      currentUserId={session.user.id}
                      password={userPasswords[user.id] || ""}
                      onPasswordChange={(password) => setUserPasswords({ ...userPasswords, [user.id]: password })}
                      onToggleActive={() => updateUser(user.id, { is_active: !user.is_active })}
                      onToggleRole={() => updateUser(user.id, { role: user.role === "super_admin" ? "library_staff" : "super_admin" })}
                      onResetPassword={() => resetUserPassword(user.id)}
                    />
                  ))}
                  {users.length === 0 ? <EmptyLine icon={<UsersRound size={16} />} text="No users returned by the backend yet." /> : null}
                </div>
              </div>
            </section>
          ) : null}

          {activeView === "settings" ? (
            <section className="grid gap-5 lg:grid-cols-[420px_1fr]">
              <form onSubmit={changeOwnPassword} className="panel p-5">
                <p className="label">Account</p>
                <h2 className="mt-1 text-xl font-extrabold">Change Password</h2>
                <input className="control mt-4" type="password" placeholder="Current password" value={accountPassword.current_password} onChange={(event) => setAccountPassword({ ...accountPassword, current_password: event.target.value })} required />
                <input className="control mt-3" type="password" placeholder="New password" value={accountPassword.new_password} onChange={(event) => setAccountPassword({ ...accountPassword, new_password: event.target.value })} required />
                <input className="control mt-3" type="password" placeholder="Confirm new password" value={accountPassword.confirm_password} onChange={(event) => setAccountPassword({ ...accountPassword, confirm_password: event.target.value })} required />
                <button className="btn-secondary mt-4 w-full" disabled={busy}>
                  {busy ? <Loader2 className="animate-spin" size={16} /> : <KeyRound size={16} />}
                  Change Password
                </button>
              </form>
              {session.user.role === "super_admin" ? (
                <section className="panel p-5">
                  <p className="label">Sources</p>
                  <h2 className="mt-1 text-xl font-extrabold">Discovery Connectors</h2>
                  <div className="mt-4 grid gap-3">
                    {sources.map((source) => (
                      <SourceToggle key={source.id} source={source} onSave={updateSource} />
                    ))}
                  </div>
                </section>
              ) : null}
            </section>
          ) : null}

          {activeView === "reports" ? (
            <section className="grid gap-5 lg:grid-cols-2">
              {evaluation ? <EvaluationPanel evaluation={evaluation} /> : null}
              <ActivityPanel activity={activity} />
              <ExportPanel exports={exports} onDownload={downloadStoredExport} />
            </section>
          ) : null}

          {activeView === "courses" ? (
            <>
              <section className="panel p-5 md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="label">Course Compacts</p>
                    <h2 className="mt-1 text-2xl font-extrabold text-library-ink">Uploaded courses</h2>
                    <p className="mt-2 text-sm leading-6 text-library-muted">{courses.length} course{courses.length === 1 ? "" : "s"} available</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="btn-secondary" onClick={() => refreshCourses()} title="Refresh courses" aria-label="Refresh courses">
                      <RefreshCw className={busy ? "animate-spin" : undefined} size={16} />
                      Refresh
                    </button>
                    <a className="btn-primary" href="/upload-compact">
                      <FileUp size={16} />
                      Upload Compact
                    </a>
                  </div>
                </div>
                <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {courses.map((course) => (
                    <button
                      key={course.id}
                      className={`rounded-lg border p-4 text-left transition ${
                        selectedCourseId === course.id
                          ? "border-library-purple bg-library-purple/10 shadow-soft"
                          : "border-library-line bg-white hover:border-library-purple/30 hover:bg-library-paper"
                      }`}
                      onClick={() => loadCourse(course.id)}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-extrabold text-library-ink">{course.course_code}</p>
                          <p className="mt-1 line-clamp-2 text-sm text-library-muted">{course.course_title}</p>
                        </div>
                        <FolderOpen className="mt-0.5 shrink-0 text-library-purple" size={16} />
                      </div>
                      <p className="mt-3 text-xs font-bold uppercase tracking-[0.12em] text-library-purple">{statusLabel(course.status)}</p>
                    </button>
                  ))}
                  {courses.length === 0 ? <EmptyLine icon={<FolderOpen size={16} />} text="No compacts uploaded yet." /> : null}
                </div>
              </section>

              {selectedCourse ? (
                <section className="panel overflow-hidden">
                  <div className="border-b border-library-line bg-white px-5 py-5 md:px-6">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                      <div>
                        <p className="label">Selected Course</p>
                        <h2 className="mt-2 text-2xl font-extrabold leading-tight text-library-ink md:text-3xl">{selectedCourse.course_title}</h2>
                        <p className="mt-2 max-w-3xl text-sm leading-6 text-library-muted">
                          {selectedCourse.course_code} · {selectedCourse.department || "Department pending"} · {statusLabel(selectedCourse.status)}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          className="btn-secondary"
                          disabled={!selectedCourseId || isArchivedCourse || busy}
                          onClick={confirmTopics}
                          title={isArchivedCourse ? "Restore this course before confirming topics" : undefined}
                        >
                          {busy ? <Loader2 className="animate-spin" size={16} /> : <Check size={16} />}
                          Confirm Topics
                        </button>
                        <button className="btn-primary" disabled={!selectedCourseId || !canGenerateResources || busy} onClick={generateResources} title={generateResourcesTitle}>
                          {busy ? <Loader2 className="animate-spin" size={16} /> : <Search size={16} />}
                          Generate Resources
                        </button>
                        <button className="btn-secondary" disabled={!selectedCourseId || busy} onClick={archiveOrRestoreCourse}>
                          {selectedCourse.status === "archived" ? "Restore" : "Archive"}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-0 border-b border-library-line md:grid-cols-4">
                    <StatCard icon={<Database size={18} />} label="Courses" value={stats.courses} />
                    <StatCard icon={<BookOpen size={18} />} label="Topics" value={stats.topics} />
                    <StatCard icon={<Settings2 size={18} />} label="Pending Review" value={stats.pending} />
                    <StatCard icon={<UsersRound size={18} />} label="Approved" value={stats.approved} />
                  </div>

                  <div className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center md:justify-between md:px-6">
                    <p className="rounded-lg bg-library-paper px-3 py-2 text-sm text-library-muted" aria-live="polite">
                      {busy ? <Loader2 className="mr-2 inline animate-spin text-library-purple" size={15} /> : null}
                      {message}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <button className="btn-secondary" disabled={!selectedCourseId || isArchivedCourse || !hasApprovedResources || busy} onClick={exportJson} title={exportTitle}>
                        <Download size={16} />
                        JSON
                      </button>
                      <button className="btn-secondary" disabled={!selectedCourseId || isArchivedCourse || !hasApprovedResources || busy} onClick={exportCsv} title={exportTitle}>
                        <Download size={16} />
                        CSV
                      </button>
                      <button className="btn-secondary" disabled={!selectedCourseId || isArchivedCourse || !hasApprovedResources || busy} onClick={exportHtml} title={exportTitle}>
                        <Download size={16} />
                        HTML
                      </button>
                    </div>
                  </div>

                  {job ? (
                    <div className="mx-5 mb-5 rounded-xl border border-library-purple/15 bg-library-purple/5 p-4 md:mx-6">
                      <div className="flex items-center justify-between gap-3 text-sm font-bold">
                        <span className="inline-flex items-center gap-2 text-library-ink">
                          <Loader2 className="animate-spin text-library-purple" size={16} />
                          {job.message || job.job_type}
                        </span>
                        <span className="text-library-purple">{job.progress}%</span>
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white">
                        <div className="h-full rounded-full bg-library-purple transition-all" style={{ width: `${job.progress}%` }} />
                      </div>
                      {job.error_message ? <p className="mt-2 text-sm text-red-700">{job.error_message}</p> : null}
                    </div>
                  ) : null}

                  {isArchivedCourse ? (
                    <div className="mx-5 mb-5 rounded-xl border border-library-gold/30 bg-library-gold/10 px-4 py-3 text-sm text-library-ink/75 md:mx-6">
                      <p className="font-bold text-library-ink">Archived course is read-only.</p>
                      <p className="mt-1">Restore it before editing topics, resources, metadata, or generating new exports.</p>
                    </div>
                  ) : null}

                  <div className="px-5 pb-5 md:px-6">
                    <CourseMetadataEditor course={selectedCourse} onSave={updateCourse} readOnly={isArchivedCourse} />
                  </div>
                </section>
              ) : null}

          {detail ? (
            <section className="grid gap-5 xl:grid-cols-[1fr_1fr]">
              <div className="space-y-4">
                <div className="panel p-5">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <p className="label">Extracted Topics</p>
                      <h3 className="text-xl font-bold">Edit Before Search</h3>
                    </div>
                    <BookOpen className="text-library-purple" />
                  </div>
                  <div className="space-y-3">
                    {detail.topics.map((topic) => (
                      <TopicEditor key={topic.id} topic={topic} onSave={updateTopic} onDelete={deleteTopic} readOnly={isArchivedCourse} />
                    ))}
                  </div>
                  <form onSubmit={addTopic} className="mt-4 rounded-xl border border-library-line bg-library-purple/5 p-3">
                    <p className="text-sm font-bold text-library-purple">Add missing topic from compact</p>
                    <div className="mt-3 grid gap-2 md:grid-cols-[90px_1fr]">
                      <input
                        className="control"
                        placeholder="Week"
                        value={newTopic.week_number}
                        disabled={isArchivedCourse}
                        onChange={(event) => setNewTopic({ ...newTopic, week_number: event.target.value })}
                      />
                      <input
                        className="control"
                        placeholder="Topic title"
                        value={newTopic.topic_title}
                        disabled={isArchivedCourse}
                        onChange={(event) => setNewTopic({ ...newTopic, topic_title: event.target.value })}
                        required
                      />
                      <input
                        className="control md:col-span-2"
                        placeholder="Module title"
                        value={newTopic.module_title}
                        disabled={isArchivedCourse}
                        onChange={(event) => setNewTopic({ ...newTopic, module_title: event.target.value })}
                      />
                      <input
                        className="control md:col-span-2"
                        placeholder="Subtopics separated by semicolon"
                        value={newTopic.subtopics}
                        disabled={isArchivedCourse}
                        onChange={(event) => setNewTopic({ ...newTopic, subtopics: event.target.value })}
                      />
                    </div>
                    <button className="btn-secondary mt-3" disabled={busy || isArchivedCourse}>
                      <Plus size={16} />
                      Add Topic
                    </button>
                  </form>
                </div>

                <form onSubmit={addManualResource} className="panel p-5">
                  <p className="label">Manual Resource</p>
                  <h3 className="text-xl font-bold">Add Approved Item</h3>
                  {!hasSearchableTopics ? (
                    <p className="mt-2 rounded-lg bg-library-paper px-3 py-2 text-sm text-library-muted">
                      Mark at least one teaching topic as searchable before adding manual resources.
                    </p>
                  ) : null}
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <select
                      className="control"
                      value={manualResource.topic_id}
                      disabled={isArchivedCourse || !hasSearchableTopics}
                      onChange={(event) => setManualResource({ ...manualResource, topic_id: event.target.value })}
                      required
                    >
                      <option value="">Select topic</option>
                      {searchableTopics.map((topic) => (
                        <option value={topic.id} key={topic.id}>
                          Week {topic.week_number || "-"} · {topic.topic_title}
                        </option>
                      ))}
                    </select>
                    <select
                      className="control"
                      value={manualResource.category}
                      disabled={isArchivedCourse}
                      onChange={(event) => setManualResource({ ...manualResource, category: event.target.value })}
                    >
                      {categories.map((category) => (
                        <option key={category}>{category}</option>
                      ))}
                    </select>
                    <input
                      className="control md:col-span-2"
                      placeholder="Resource title"
                      value={manualResource.title}
                      disabled={isArchivedCourse}
                      onChange={(event) => setManualResource({ ...manualResource, title: event.target.value })}
                      required
                    />
                    <input
                      className="control"
                      placeholder="Authors, separated by semicolon"
                      value={manualResource.authors}
                      disabled={isArchivedCourse}
                      onChange={(event) => setManualResource({ ...manualResource, authors: event.target.value })}
                    />
                    <input
                      className="control"
                      placeholder="Year"
                      value={manualResource.year}
                      disabled={isArchivedCourse}
                      onChange={(event) => setManualResource({ ...manualResource, year: event.target.value })}
                    />
                    <input
                      className="control md:col-span-2"
                      placeholder="URL"
                      value={manualResource.url}
                      disabled={isArchivedCourse}
                      onChange={(event) => setManualResource({ ...manualResource, url: event.target.value })}
                    />
                  </div>
                  <button className="btn-gold mt-3" disabled={busy || isArchivedCourse || !hasSearchableTopics}>
                    <Plus size={16} />
                    Add Approved Resource
                  </button>
                </form>
              </div>

              <div className="space-y-4">
                <div className="panel p-5">
                  <p className="label">Review Queue</p>
                  <h3 className="text-xl font-bold">Top 5 Per Topic</h3>
                  <div className="mt-4 space-y-5">
                    {detail.topics.map((topic) => (
                      <div key={topic.id} className="rounded-xl border border-library-line bg-library-paper p-3">
                        <div className="mb-3">
                          <p className="text-xs font-bold uppercase text-library-purple">Week {topic.week_number || "-"}</p>
                          <h4 className="font-bold">{topic.topic_title}</h4>
                        </div>
                        <div className="space-y-2">
                          {(candidatesByTopic[topic.id] || []).map((candidate) => (
                            <CandidateEditor
                              key={candidate.id}
                              candidate={candidate}
                              onSave={updateCandidate}
                              onApprove={(item) => reviewCandidate(item, "approve")}
                              onReject={(item) => reviewCandidate(item, "reject")}
                              readOnly={isArchivedCourse}
                            />
                          ))}
                          {(candidatesByTopic[topic.id] || []).length === 0 ? (
                            <p className="text-sm text-library-muted">No generated resources yet.</p>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="panel p-5">
                  <p className="label">Approved Repository Records</p>
                  <h3 className="text-xl font-bold">RCAABUT Export Preview</h3>
                  <div className="mt-4 space-y-3">
                    {detail.topics.map((topic) => (
                      <ApprovedTopicPreview
                        key={topic.id}
                        topic={topic}
                        resources={approvedByTopic[topic.id] || []}
                        onSave={updateApprovedResource}
                        onDelete={deleteApprovedResource}
                        readOnly={isArchivedCourse}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </section>
          ) : null}
            </>
          ) : null}
        </section>
      </div>
    </main>
  );
}

function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <section className="rounded-lg border border-library-line bg-white px-5 py-5 shadow-soft md:px-6">
      <p className="label">{eyebrow}</p>
      <h1 className="mt-2 text-3xl font-extrabold leading-tight text-library-ink md:text-4xl">{title}</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-library-muted md:text-base">{description}</p>
    </section>
  );
}

function ActivityPanel({ activity }: { activity: ActivityLog[] }) {
  return (
    <div className="panel p-5">
      <p className="label">Activity Log</p>
      <h3 className="text-xl font-bold">Recent Actions</h3>
      <div className="mt-4 space-y-2">
        {activity.slice(0, 8).map((item) => (
          <div key={item.id} className="rounded-xl border border-library-line bg-library-paper p-3 text-sm">
            <p className="font-semibold">{item.action.replaceAll("_", " ")}</p>
            <p className="mt-1 text-library-muted">
              {item.actor} · {new Date(item.created_at).toLocaleString()}
            </p>
          </div>
        ))}
        {activity.length === 0 ? <p className="text-sm text-library-muted">No activity recorded yet.</p> : null}
      </div>
    </div>
  );
}

function ExportPanel({
  exports,
  onDownload
}: {
  exports: ExportHistory[];
  onDownload: (item: ExportHistory) => Promise<void>;
}) {
  return (
    <div className="panel p-5">
      <p className="label">Export History</p>
      <h3 className="text-xl font-bold">Generated Files</h3>
      <div className="mt-4 space-y-2">
        {exports.slice(0, 8).map((item) => (
          <div key={item.id} className="rounded-xl border border-library-line bg-library-paper p-3 text-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold">{item.export_type.toUpperCase()} export</p>
                <p className="mt-1 text-library-muted">
                  {item.course} · {item.created_by}
                </p>
              </div>
              <button className="rounded-md border border-library-line bg-white px-2 py-1 font-bold text-library-purple" onClick={() => onDownload(item)}>
                Download
              </button>
            </div>
          </div>
        ))}
        {exports.length === 0 ? <p className="text-sm text-library-muted">No exports generated yet.</p> : null}
      </div>
    </div>
  );
}

function EvaluationPanel({ evaluation }: { evaluation: EvaluationReport }) {
  return (
    <div className="panel p-5 lg:col-span-2">
      <p className="label">Evaluation</p>
      <h3 className="text-xl font-bold">Prototype Metrics</h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Avg. job time" value={`${evaluation.summary.average_completed_job_seconds}s`} />
        <Metric label="Extraction confidence" value={`${Math.round(evaluation.summary.average_extraction_confidence * 100)}%`} />
        <Metric label="Candidates / topic" value={evaluation.summary.average_candidates_per_searchable_topic.toString()} />
        <Metric label="Approval rate" value={`${Math.round(evaluation.summary.approval_rate * 100)}%`} />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Breakdown title="Sources" rows={evaluation.source_breakdown} />
        <Breakdown title="Categories" rows={evaluation.category_breakdown} />
      </div>
    </div>
  );
}

function UserManagementRow({
  user,
  currentUserId,
  password,
  onPasswordChange,
  onToggleActive,
  onToggleRole,
  onResetPassword
}: {
  user: User;
  currentUserId: number;
  password: string;
  onPasswordChange: (password: string) => void;
  onToggleActive: () => void;
  onToggleRole: () => void;
  onResetPassword: () => void;
}) {
  const isCurrentUser = user.id === currentUserId;

  return (
    <div className="rounded-lg border border-library-line bg-library-paper p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-extrabold text-library-ink">{user.full_name}</p>
          <p className="mt-1 text-library-muted">
            {roleLabel(user.role)} · {user.is_active ? "Active" : "Inactive"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md border border-library-line bg-white px-2 py-1 font-bold text-library-purple disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isCurrentUser}
            onClick={onToggleActive}
            title={isCurrentUser ? "You cannot disable your own account" : undefined}
          >
            {isCurrentUser ? "Current" : user.is_active ? "Disable" : "Enable"}
          </button>
          {!isCurrentUser ? (
            <button type="button" className="rounded-md border border-library-line bg-white px-2 py-1 font-bold text-library-purple" onClick={onToggleRole}>
              Make {user.role === "super_admin" ? "Library Staff" : "Super Admin"}
            </button>
          ) : null}
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
        <input className="control text-xs" type="password" placeholder="New password" value={password} onChange={(event) => onPasswordChange(event.target.value)} />
        <button type="button" className="rounded-md border border-library-line bg-white px-3 py-2 font-bold text-library-purple" onClick={onResetPassword}>
          Reset
        </button>
      </div>
    </div>
  );
}

function BrandLogo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center">
      <img
        src="/covenant-clr-logo.png"
        alt="Covenant Centre for Learning Resources"
        className={compact ? "h-auto w-[230px] max-w-full" : "h-auto w-[320px] max-w-full"}
      />
    </div>
  );
}

function LoadingShell() {
  return (
    <main className="min-h-screen bg-library-paper lg:grid lg:grid-cols-[304px_minmax(0,1fr)]">
      <aside className="border-b border-library-line bg-white px-4 py-5 shadow-soft lg:h-screen lg:border-b-0 lg:border-r lg:px-5">
        <div className="space-y-5">
          <BrandLogo compact />
          <div className="space-y-2">
            <div className="skeleton h-10" />
            <div className="skeleton h-10" />
            <div className="skeleton h-10" />
          </div>
          <div className="panel-flat p-4">
            <div className="skeleton h-12 w-3/4" />
            <div className="mt-4 grid grid-cols-2 gap-2">
              <div className="skeleton h-16" />
              <div className="skeleton h-16" />
            </div>
          </div>
          <div className="panel-flat p-4">
            <div className="skeleton h-8 w-32" />
            <div className="mt-4 space-y-3">
              <div className="skeleton h-20" />
              <div className="skeleton h-20" />
              <div className="skeleton h-20" />
            </div>
          </div>
        </div>
      </aside>
      <div className="min-w-0 px-4 py-5 md:px-6 lg:px-8">
        <section className="panel overflow-hidden">
          <div className="border-b border-library-line px-5 py-6 md:px-6">
            <div className="skeleton h-5 w-48" />
            <div className="skeleton mt-4 h-11 w-3/4" />
            <div className="skeleton mt-3 h-5 w-1/2" />
          </div>
          <div className="grid gap-0 border-b border-library-line md:grid-cols-4">
            {[0, 1, 2, 3].map((item) => (
              <div key={item} className="border-b border-library-line p-5 md:border-b-0 md:border-r">
                <div className="skeleton h-4 w-24" />
                <div className="skeleton mt-3 h-9 w-16" />
              </div>
            ))}
          </div>
          <div className="p-5 md:p-6">
            <div className="skeleton h-64" />
          </div>
        </section>
      </div>
    </main>
  );
}

function WelcomeEmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-library-line bg-library-paper px-5 py-8 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-white text-library-purple shadow-soft">
        <FileUp size={22} />
      </div>
      <h2 className="mt-4 text-xl font-extrabold text-library-ink">No course selected yet</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-library-muted">
        Upload a course compact from the sidebar, or pick an existing compact to edit topics and curate resources.
      </p>
    </div>
  );
}

function EmptyLine({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dashed border-library-line bg-library-paper px-3 py-3 text-sm text-library-muted">
      <span className="text-library-purple">{icon}</span>
      {text}
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="border-b border-library-line p-5 md:border-b-0 md:border-r last:md:border-r-0">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-bold text-library-muted">{label}</p>
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-library-purple/10 text-library-purple">{icon}</span>
      </div>
      <p className="mt-3 text-3xl font-extrabold text-library-ink">{value}</p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-library-line bg-library-paper p-3">
      <p className="text-xs font-bold uppercase tracking-[0.12em] text-library-purple">{label}</p>
      <p className="mt-1 text-2xl font-extrabold text-library-ink">{value}</p>
    </div>
  );
}

function Breakdown({ title, rows }: { title: string; rows: Record<string, number> }) {
  const entries = Object.entries(rows).sort((a, b) => b[1] - a[1]).slice(0, 5);
  return (
    <div className="rounded-xl border border-library-line bg-white p-3">
      <p className="text-sm font-bold text-library-ink">{title}</p>
      <div className="mt-2 space-y-2">
        {entries.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3 text-sm">
            <span className="truncate text-library-muted">{label.replaceAll("_", " ")}</span>
            <span className="font-bold text-library-purple">{value}</span>
          </div>
        ))}
        {entries.length === 0 ? <p className="text-sm text-library-muted">No data yet.</p> : null}
      </div>
    </div>
  );
}

function CourseMetadataEditor({
  course,
  onSave,
  readOnly
}: {
  course: Course;
  onSave: (course: Course) => Promise<void>;
  readOnly: boolean;
}) {
  const [draft, setDraft] = useState(course);

  useEffect(() => {
    setDraft(course);
  }, [course]);

  return (
    <div className="mt-4 rounded-xl border border-library-line bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="label">Course Metadata</p>
          <h3 className="text-lg font-bold">Correct extracted details</h3>
        </div>
        <button className="btn-secondary" onClick={() => onSave(draft)} disabled={readOnly}>
          <Check size={16} />
          Save Metadata
        </button>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <input className="control" value={draft.course_code} disabled={readOnly} onChange={(event) => setDraft({ ...draft, course_code: event.target.value })} />
        <input className="control" value={draft.course_title} disabled={readOnly} onChange={(event) => setDraft({ ...draft, course_title: event.target.value })} />
        <input
          className="control"
          placeholder="College"
          value={draft.college || ""}
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, college: event.target.value })}
        />
        <input
          className="control"
          placeholder="Department"
          value={draft.department || ""}
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, department: event.target.value })}
        />
        <input
          className="control"
          placeholder="Programme"
          value={draft.programme || ""}
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, programme: event.target.value })}
        />
        <input
          className="control"
          placeholder="Level"
          value={draft.level || ""}
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, level: event.target.value })}
        />
        <input
          className="control"
          placeholder="Semester"
          value={draft.semester || ""}
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, semester: event.target.value })}
        />
        <input
          className="control"
          placeholder="Session"
          value={draft.session || ""}
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, session: event.target.value })}
        />
        <input
          className="control md:col-span-2"
          placeholder="Lecturers separated by semicolon"
          value={draft.lecturers.join("; ")}
          disabled={readOnly}
          onChange={(event) =>
            setDraft({
              ...draft,
              lecturers: event.target.value
                .split(";")
                .map((item) => item.trim())
                .filter(Boolean)
            })
          }
        />
        <textarea
          className="control md:col-span-2"
          rows={2}
          placeholder="Course description"
          value={draft.description || ""}
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, description: event.target.value })}
        />
      </div>
    </div>
  );
}

function SourceToggle({ source, onSave }: { source: SourceConfig; onSave: (source: SourceConfig) => Promise<void> }) {
  const [draft, setDraft] = useState(source);

  useEffect(() => {
    setDraft(source);
  }, [source]);

  return (
    <div className="rounded-xl border border-library-line bg-library-paper p-3 text-xs">
      <div className="flex items-start justify-between gap-2">
        <div>
          <strong>{draft.display_name}</strong>
          <span className="block text-library-muted">
            {draft.source_type} · {draft.is_enabled ? "Enabled" : "Disabled"}
          </span>
        </div>
        <label className="flex items-center gap-2 font-bold text-library-purple">
          <input
            type="checkbox"
            checked={draft.is_enabled}
            onChange={(event) => setDraft({ ...draft, is_enabled: event.target.checked })}
          />
          Use
        </label>
      </div>
      <textarea
        className="control mt-2 min-h-16 text-xs"
        value={draft.notes || ""}
        onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
      />
      <button type="button" className="mt-2 rounded-md border border-library-line bg-white px-2 py-1 font-bold text-library-purple" onClick={() => onSave(draft)}>
        Save Source
      </button>
    </div>
  );
}

function TopicEditor({
  topic,
  onSave,
  onDelete,
  readOnly
}: {
  topic: Topic;
  onSave: (topic: Topic) => Promise<void>;
  onDelete: (topicId: number) => Promise<void>;
  readOnly: boolean;
}) {
  const [draft, setDraft] = useState(topic);
  const subtopicsText = draft.subtopics.join("; ");

  useEffect(() => {
    setDraft(topic);
  }, [topic]);

  return (
    <div className="rounded-xl border border-library-line bg-library-paper p-3">
      <div className="grid gap-2 md:grid-cols-[90px_1fr]">
        <input
          className="control"
          value={draft.week_number ?? ""}
          placeholder="Week"
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, week_number: event.target.value ? Number(event.target.value) : null })}
        />
        <input
          className="control font-semibold"
          value={draft.topic_title}
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, topic_title: event.target.value })}
        />
        <input
          className="control md:col-span-2"
          value={draft.module_title || ""}
          placeholder="Module title"
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, module_title: event.target.value })}
        />
        <textarea
          className="control md:col-span-2"
          rows={2}
          value={subtopicsText}
          placeholder="Subtopics separated by semicolon"
          disabled={readOnly}
          onChange={(event) =>
            setDraft({
              ...draft,
              subtopics: event.target.value
                .split(";")
                .map((item) => item.trim())
                .filter(Boolean)
            })
          }
        />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.is_searchable}
            disabled={readOnly}
            onChange={(event) => setDraft({ ...draft, is_searchable: event.target.checked })}
          />
          Searchable
        </label>
        <button className="btn-secondary" onClick={() => onSave(draft)} disabled={readOnly}>
          <Check size={16} />
          Save
        </button>
        <button className="rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onDelete(topic.id)} disabled={readOnly}>
          <X size={16} />
        </button>
      </div>
    </div>
  );
}

function CandidateEditor({
  candidate,
  onSave,
  onApprove,
  onReject,
  readOnly
}: {
  candidate: CandidateResource;
  onSave: (candidate: CandidateResource) => Promise<void>;
  onApprove: (candidate: CandidateResource) => Promise<void>;
  onReject: (candidate: CandidateResource) => Promise<void>;
  readOnly: boolean;
}) {
  const [draft, setDraft] = useState(candidate);

  useEffect(() => {
    setDraft(candidate);
  }, [candidate]);

  return (
    <div className="rounded-xl border border-library-line bg-white p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="grid gap-2 md:grid-cols-[180px_1fr]">
            <select className="control" value={draft.category} disabled={readOnly} onChange={(event) => setDraft({ ...draft, category: event.target.value })}>
              {categories.map((category) => (
                <option key={category}>{category}</option>
              ))}
            </select>
            <input className="control font-bold" value={draft.title} disabled={readOnly} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
            <input
              className="control"
              placeholder="Year"
              value={draft.year || ""}
              disabled={readOnly}
              onChange={(event) => setDraft({ ...draft, year: event.target.value ? Number(event.target.value) : null })}
            />
            <input
              className="control"
              placeholder="Authors separated by semicolon"
              value={draft.authors.join("; ")}
              disabled={readOnly}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  authors: event.target.value
                    .split(";")
                    .map((item) => item.trim())
                    .filter(Boolean)
                })
              }
            />
            <input className="control md:col-span-2" placeholder="URL" value={draft.url || ""} disabled={readOnly} onChange={(event) => setDraft({ ...draft, url: event.target.value })} />
            <textarea
              className="control md:col-span-2"
              rows={2}
              placeholder="Match reason"
              value={draft.match_reason || ""}
              disabled={readOnly}
              onChange={(event) => setDraft({ ...draft, match_reason: event.target.value })}
            />
          </div>
          <p className="mt-2 text-xs text-library-muted">
            {draft.source_system} · score {draft.relevance_score} · {draft.status}
          </p>
        </div>
        <div className="flex shrink-0 flex-col gap-1">
          <button className="rounded-lg bg-library-purple p-2 text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onApprove(draft)} title="Approve" disabled={readOnly}>
            <Check size={16} />
          </button>
          <button className="rounded-lg border border-library-line bg-white p-2 text-library-purple disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onSave(draft)} title="Save edits" disabled={readOnly}>
            <Edit3 size={16} />
          </button>
          <button className="rounded-lg bg-red-700 p-2 text-white disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onReject(draft)} title="Reject" disabled={readOnly}>
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

function ApprovedTopicPreview({
  topic,
  resources,
  onSave,
  onDelete,
  readOnly
}: {
  topic: Topic;
  resources: ApprovedResource[];
  onSave: (resource: ApprovedResource) => Promise<void>;
  onDelete: (resourceId: number) => Promise<void>;
  readOnly: boolean;
}) {
  const knownCategoryGroups = categories
    .map((category) => ({
      category,
      resources: resources.filter((resource) => resource.category === category)
    }))
    .filter((group) => group.resources.length > 0);
  const uncategorised = resources.filter((resource) => !categories.includes(resource.category));
  const categoryGroups = uncategorised.length
    ? [...knownCategoryGroups, { category: "Uncategorised", resources: uncategorised }]
    : knownCategoryGroups;

  return (
    <div className="rounded-xl border border-library-line bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase text-library-purple">Week {topic.week_number || "-"}</p>
          <h4 className="font-bold">{topic.topic_title}</h4>
          {topic.module_title ? <p className="mt-1 text-xs text-library-muted">{topic.module_title}</p> : null}
        </div>
        <span className="rounded-full border border-library-purple/15 bg-library-purple/10 px-2 py-1 text-xs font-semibold text-library-purple">
          {resources.length} approved
        </span>
      </div>
      {categoryGroups.length ? (
        <div className="mt-3 space-y-3">
          {categoryGroups.map((group) => (
            <div key={group.category} className="rounded-xl bg-library-paper p-3">
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-library-purple">{group.category}</p>
                <span className="text-xs font-semibold text-library-muted">{group.resources.length}</span>
              </div>
              <ol className="space-y-2">
                {group.resources.map((resource, index) => (
                  <ApprovedResourceEditor
                    key={resource.id}
                    resource={resource}
                    resourceNumber={index + 1}
                    onSave={onSave}
                    onDelete={onDelete}
                    readOnly={readOnly}
                  />
                ))}
              </ol>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 rounded-lg bg-library-paper px-3 py-2 text-sm text-library-muted">
          No approved resources for this topic yet.
        </p>
      )}
    </div>
  );
}

function ApprovedResourceEditor({
  resource,
  resourceNumber,
  onSave,
  onDelete,
  readOnly
}: {
  resource: ApprovedResource;
  resourceNumber: number;
  onSave: (resource: ApprovedResource) => Promise<void>;
  onDelete: (resourceId: number) => Promise<void>;
  readOnly: boolean;
}) {
  const [draft, setDraft] = useState(resource);

  useEffect(() => {
    setDraft(resource);
  }, [resource]);

  return (
    <li className="rounded-xl border border-library-line bg-white p-3 text-sm">
      <div className="mb-2 flex items-center gap-2 text-xs font-bold text-library-purple">
        <span className="grid h-6 w-6 place-items-center rounded-full bg-library-purple/10">{resourceNumber}</span>
        <span>Repository item</span>
      </div>
      <div className="grid gap-2 md:grid-cols-[160px_1fr]">
        <select className="control" value={draft.category} disabled={readOnly} onChange={(event) => setDraft({ ...draft, category: event.target.value })}>
          {categories.map((category) => (
            <option key={category}>{category}</option>
          ))}
        </select>
        <input className="control font-semibold" value={draft.title} disabled={readOnly} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
        <input
          className="control"
          placeholder="Year"
          value={draft.year || ""}
          disabled={readOnly}
          onChange={(event) => setDraft({ ...draft, year: event.target.value ? Number(event.target.value) : null })}
        />
        <input
          className="control"
          placeholder="Authors separated by semicolon"
          value={draft.authors.join("; ")}
          disabled={readOnly}
          onChange={(event) =>
            setDraft({
              ...draft,
              authors: event.target.value
                .split(";")
                .map((item) => item.trim())
                .filter(Boolean)
            })
          }
        />
        <input className="control md:col-span-2" placeholder="URL" value={draft.url || ""} disabled={readOnly} onChange={(event) => setDraft({ ...draft, url: event.target.value })} />
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <button className="rounded-md border border-library-line bg-white px-2 py-1 font-bold text-library-purple disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onSave(draft)} disabled={readOnly}>
          Save approved
        </button>
        <button className="rounded-md border border-red-200 bg-white px-2 py-1 font-bold text-red-700 disabled:cursor-not-allowed disabled:opacity-50" onClick={() => onDelete(resource.id)} disabled={readOnly}>
          Remove
        </button>
      </div>
    </li>
  );
}
